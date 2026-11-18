"""The Supervisor: moves every episode through the agents, with retry limits and atomic claims.

planned → writing → (Writer ⇄ Critic, Safety gate) → scripted → rendering → (QA) → review
       → approved (publish_at) → publishing → published          side exits: failed, rejected

Episode kinds: "episode" (10-15 min), "short" (the song cut vertical, for discovery), "compilation" (long,
for watch time). Dubbed language editions hang off an episode (episode.editions[lang]).
"""
from __future__ import annotations

import shutil
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, storage
from .db import get_db, now_iso
from .kids import categories, critic, meta as metamod, planner, safety, writer
from .llm.router import LLMBusy, PROVIDERS
from .settings import app_settings, secret

ACTIVE = ("writing", "rendering", "publishing")
_lock = threading.Lock()
_current: dict = {}


def log(msg: str, level: str = "info", ep: str | None = None):
    get_db().log(msg, level, ep)


def has_ai() -> bool:
    return any(secret(p.key_env) for p in PROVIDERS.values())


def _progress(eid: str):
    def f(stage: str, pct: int):
        _current.update({"id": eid, "stage": stage, "pct": pct})
        try:
            get_db().update("episodes", eid, {"progress": {"stage": stage, "pct": pct}})
        except Exception:  # noqa: BLE001
            pass
    return f


# ---------------------------------------------------------------- create
def create(category: str | None = None, topic: str | None = None, age_band: str | None = None,
           minutes: float | None = None, why: str = "Requested", source: dict | None = None,
           art_style: str | None = None, animation: str | None = None, ai_budget_usd: float | None = None,
           palette: str | None = None) -> dict:
    s = app_settings()
    if source:
        category, topic = "books", source["title"]
    plan = planner.next_episode(age_band, category, topic)
    from .kids import optimizer
    var = optimizer.variant(plan["age_band"])
    ep = get_db().insert("episodes", {
        "kind": "episode", "status": "planned", "category": plan["category"], "topic": plan["topic"],
        "age_band": plan["age_band"], "language": s.get("language", "en"),
        "minutes": float(minutes or var["minutes"] or s.get("target_minutes", 12)), "variant": var,
        "why": ((why if why.startswith("Book series") else f"Book: {source['book']}") if source else plan.get("why")) or why, "source": source,
        "angle": plan.get("angle", ""),
        "art_style": art_style or s.get("art_style", "auto"), "animation": animation or s.get("animation", "code"),
        "palette": palette or s.get("palette", "auto"),
        **({"ai_budget_usd": float(ai_budget_usd)} if ai_budget_usd is not None else {}),
        "editions": {}, "progress": {"stage": "planned", "pct": 0}})
    planner.remember(plan["topic"], plan["category"], ep["id"])
    log(f"Planned: {plan['topic']} ({plan['category']}, {plan['age_band']}) — {plan.get('why')}", ep=ep["id"])
    return ep


# ---------------------------------------------------------------- write
def write(eid: str) -> dict:
    db = get_db()
    ep = db.claim("episodes", eid, ["planned", "failed", "review", "scripted", "rejected"],
                  {"status": "writing", "error": None, "progress": {"stage": "writing", "pct": 5}})
    if not ep:
        return db.get("episodes", eid)
    s = app_settings()
    prog = _progress(eid)
    try:
        lg = lambda m: log(m, ep=eid)   # noqa: E731
        if has_ai():
            from .kids import optimizer
            script = writer.write_episode(ep["category"], ep["topic"], ep["age_band"], ep["minutes"], ep.get("language", "en"),
                                          lg, source=ep.get("source"),
                                          hints=(optimizer.writer_hints() + (f" OUR ORIGINAL ANGLE for this trending "
                                                 f"topic: {ep['angle']}" if ep.get("angle") else "")).strip())
        else:
            log("No AI key yet: using the built-in template writer (add a free Gemini/Groq key in Settings for real "
                "episodes on any topic).", "warn", eid)
            # the template only knows counting: label it honestly so title/description match the content
            script = writer.template_script("numbers", "Counting with Hoppy and Friends", ep["age_band"], ep["minutes"])
            db.update("episodes", eid, {"category": "numbers", "topic": "Counting with Hoppy and Friends (demo)"})
            ep.update(category="numbers", topic="Counting with Hoppy and Friends (demo)")
        prog("writing", 40)
        review = critic.review(script, ep["age_band"])
        bar = float(s.get("quality_bar", 7.5))
        for attempt in range(int(s.get("max_revisions", 2))):
            if review["score"] >= bar or script.get("writer") != "ai":
                break
            notes = review["segment_notes"] or critic.notes_from_metrics(script, review["metrics"])
            if not notes:
                break
            log(f"Critic {review['score']}/10 < {bar}: rewriting {len(notes)} segment(s) (round {attempt + 1})", ep=eid)
            script = writer.rewrite_segments(script, notes, lg)
            review = critic.review(script, ep["age_band"])
        prog("writing", 70)
        sim, twin = similarity_to_recent(script, eid)
        if sim > float(s.get("variety_max", .32)) and script.get("writer") == "ai":
            log(f"Too similar to a recent episode ({sim:.0%} of lines overlap {twin}): rewriting for variety", "warn", eid)
            note = ("This episode repeats too many lines from a recent one. Use NEW jokes, a NEW song with new words, "
                    "new examples and new wording; keep the rituals (hello/goodbye) but say them freshly.")
            script = writer.rewrite_segments(script, {i: note for i in range(len(script["segments"]))
                                                      if script["segments"][i]["kind"] not in ("hello", "goodbye")}, lg)
            sim, twin = similarity_to_recent(script, eid)
        review["variety"] = {"overlap": round(sim, 3), "closest": twin}
        _growth_line(script, s)
        try:
            from .kids import library
            library.attach(script)
        except Exception as e:  # noqa: BLE001
            log(f"Character library not applied: {e}", "warn", eid)
        meta = metamod.build(script, {**s, "_variant": ep.get("variant") or {}})
        gate = safety.check_episode({"script": script, "meta": meta})
        status = "scripted" if gate["ok"] else "failed"
        patch = {"script": script, "critic": review, "safety": gate, "meta": meta, "status": status,
                 "progress": {"stage": status, "pct": 75}}
        if not gate["ok"]:
            blocks = [f"{i['rule']}: '{i['word']}' in {i.get('where', '')}" for i in gate["issues"] if i["level"] == "block"]
            patch["error"] = "Safety gate blocked: " + "; ".join(blocks[:4])
            log(patch["error"], "error", eid)
        else:
            log(f"Script ready: critic {review['score']}/10, ~{review['metrics']['est_minutes']} min, "
                f"{review['metrics']['questions']} questions", ep=eid)
        out = db.update("episodes", eid, patch)
        try:
            from .kids import library
            ids = library.harvest(script, eid, ep.get("source"))
            if ids:
                log(f"Characters saved to the library: {', '.join(ids)}", ep=eid)
        except Exception as e:  # noqa: BLE001
            log(f"Could not save characters to the library: {e}", "warn", eid)
        return out
    except LLMBusy as e:
        log(f"AI providers busy, will retry: {str(e)[:200]}", "warn", eid)
        return db.update("episodes", eid, {"status": "planned", "progress": {"stage": "waiting for AI", "pct": 0}})
    except Exception as e:  # noqa: BLE001
        log(f"Writing failed: {e}\n{traceback.format_exc()[-800:]}", "error", eid)
        return db.update("episodes", eid, {"status": "failed", "error": f"Writing failed: {str(e)[:300]}"})


def _growth_line(script: dict, s: dict):
    """One gentle, parent-directed subscribe line just before the final goodbye (growth_cta)."""
    if not s.get("growth_cta", True) or not script.get("segments"):
        return
    last = script["segments"][-1]
    if last["kind"] != "goodbye" or any(sc.get("_cta") for sc in last["scenes"]):
        return
    line = s.get("cta_line") or "Grown-ups, tap subscribe so we can play again soon!"
    last["scenes"].insert(max(0, len(last["scenes"]) - 1), {
        "speaker": "sunny", "text": line, "kind": "line", "emotion": "happy", "action": "wave",
        "cast": last["scenes"][-1].get("cast") or ["pip", "mimi"], "card": None, "_cta": True})


# ---------------------------------------------------------------- render
def render(eid: str) -> dict:
    db = get_db()
    ep = db.claim("episodes", eid, ["scripted", "review", "failed", "approved"],
                  {"status": "rendering", "error": None, "progress": {"stage": "rendering", "pct": 5}})
    if not ep:
        return db.get("episodes", eid)
    if not ep.get("script"):
        return db.update("episodes", eid, {"status": "planned"})
    s = app_settings()
    work = config.WORK_DIR / eid
    prog = _progress(eid)
    try:
        from .render import episode as epr
        var = ep.get("variant") or {}
        rs = {**s, "_meta": ep.get("meta") or {}, "_pace": var.get("pace") or s.get("pace"), "_thumb": var.get("thumb", "face"),
              "_style": style_for(ep, s), "_animation": ep.get("animation") or s.get("animation", "code"),
              "_ai_budget": ep.get("ai_budget_usd"), "_palette": palette_for(ep, s)}
        if s.get("ai_backgrounds"):
            from .render import aiart
            rs["_bg_images"] = aiart.prepare(ep["script"], work, rs["_style"], lambda m: log(m, ep=eid))
        out = epr.render(ep["script"], rs, work, lambda m: log(m, ep=eid), prog)
        ai_video = {"mode": "code"}
        if rs["_animation"] in ("hero", "full"):
            from .render import aivideo
            prog("AI animation", 88)
            ai_video = aivideo.enhance(ep["script"], out, rs, work, lambda m, lvl="info": log(m, lvl, eid))
        prog("uploading", 92)
        key = f"{eid}/episode-{int(time.time())}.mp4"
        video_url = storage.put(out["video"], key, "video/mp4")
        thumb_url = storage.put(out["thumb"], f"{eid}/thumb-{int(time.time())}.jpg", "image/jpeg")
        timeline = out["segments"]
        meta = dict(ep.get("meta") or metamod.build(ep["script"], s))
        meta = {**metamod.build(ep["script"], {**s, "_variant": var}, timeline),
                **{k: meta[k] for k in ("title", "tags", "thumb_text") if meta.get(k)}}
        meta["localizations"] = metamod.localize(meta, s.get("localize_languages") or []) if has_ai() else {}
        qa = run_qa(ep, out, s)
        patch = {"video_url": video_url, "thumb_url": thumb_url, "duration": round(out["duration"], 1), "timeline": timeline,
                 "song_regions": out["song_regions"], "meta": meta, "qa": qa, "engines": out["engines"],
                 "ai_video": ai_video, "rendered_style": rs["_style"], "rendered_palette": rs["_palette"],
                 "status": "review", "progress": {"stage": "review", "pct": 100}, "rendered_at": now_iso()}
        old = [u for u in (ep.get("video_url"), ep.get("thumb_url")) if u and u not in (video_url, thumb_url)]
        ep = db.update("episodes", eid, patch)
        if old:
            try:                                   # the replaced render is never used again: free its space now
                from . import janitor
                storage.remove([k for k in map(janitor.key_of, old) if k])
            except Exception as e:  # noqa: BLE001
                log(f"Old render not removed (the daily cleanup will retry): {e}", "warn", eid)
        log(f"Rendered {out['duration'] / 60:.1f} min ({'all checks passed' if qa['ok'] else 'QA issues'})", ep=eid)
        if not ep.get("edition_of") and has_ai():
            for lang in s.get("editions") or []:
                if lang != ep.get("language", "en") and lang not in (ep.get("editions") or {}):
                    try:
                        make_edition(eid, lang)
                    except Exception as e:  # noqa: BLE001
                        log(f"{lang} edition not queued: {e}", "warn", eid)
            ep = db.get("episodes", eid)
        if s.get("autopilot") or s.get("full_auto"):
            from . import automation
            why = automation.gates(ep, s)
            if why:
                ep = db.update("episodes", eid, {"auto_hold": why})
                log("Auto: kept in Review — " + "; ".join(why), ep=eid)
            else:
                ep = approve(eid, None)
                log("Auto: approved (all gates passed) for the next posting slot", ep=eid)
        return ep
    except Exception as e:  # noqa: BLE001
        log(f"Render failed: {e}\n{traceback.format_exc()[-1200:]}", "error", eid)
        return db.update("episodes", eid, {"status": "failed", "error": f"Render failed: {str(e)[:300]}"})
    finally:
        shutil.rmtree(work, ignore_errors=True)
        _current.clear()


def style_for(ep: dict, s: dict) -> str:
    """The episode's look: its own choice, else the optimizer's pick (auto), else the channel default."""
    from .render.styles import STYLES
    own = ep.get("art_style")
    if own in STYLES:
        return own
    var = ep.get("variant") or {}
    if var.get("style") in STYLES:
        return var["style"]
    return s.get("art_style") if s.get("art_style") in STYLES else "classic"


def palette_for(ep: dict, s: dict) -> str:
    """The episode's colour palette: its own choice, else the channel default, else picked from category + age."""
    from .render import palette
    fixed = ep.get("palette") if ep.get("palette") in palette.PALETTES else \
        (s.get("palette") if s.get("palette") in palette.PALETTES else None)
    return palette.choose(ep.get("category"), ep.get("age_band"), fixed)


def run_qa(ep: dict, out: dict, s: dict) -> dict:
    checks = []
    dur = out["duration"] / 60
    # honest length check against the episode's own target (no free pass for template/demo scripts)
    try:
        target = float(ep.get("minutes") or s.get("target_minutes") or 12)
    except (TypeError, ValueError):
        target = 12.0
    lo, hi = target * .8, target * 1.35                  # 12 min target -> 9.6-16.2 min
    demo = (ep.get("script") or {}).get("writer") != "ai"
    checks.append({"name": "Length (demo)" if demo else f"Length {lo:.0f}-{hi:.0f} min", "ok": lo <= dur <= hi,
                   "detail": f"{dur:.1f} min (target {target:g}, ok {lo:.1f}-{hi:.1f})"})
    checks.append({"name": "Flash safety (≤3 big flashes/s)", "ok": out["flash"]["max_per_s"] <= 3,
                   "detail": f"max {out['flash']['max_per_s']}/s"})
    checks.append({"name": "Human-like voices", "ok": "espeak" not in out["engines"],
                   "detail": ", ".join(out["engines"])})
    checks.append({"name": "Resolution", "ok": out["H"] >= 720, "detail": f"{out['W']}x{out['H']} @ {out['fps']} fps"})
    sf = ep.get("safety") or {}
    checks.append({"name": "Safety gate", "ok": bool(sf.get("ok", True)),
                   "detail": f"{len(sf.get('issues', []))} note(s)"})
    cr = ep.get("critic") or {}
    checks.append({"name": "Child-psychology score", "ok": cr.get("score", 0) >= float(s.get("quality_bar", 7.5)),
                   "detail": f"{cr.get('score')}/10"})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


# ---------------------------------------------------------------- variety guard (inauthentic-content policy)
def _shingles(script: dict) -> set:
    import re as _re
    words = _re.findall(r"[a-z']+", " ".join(sc["text"].lower() for g in script.get("segments", [])
                                              if g["kind"] not in ("hello", "goodbye") for sc in g["scenes"]))
    return {" ".join(words[i:i + 4]) for i in range(max(0, len(words) - 3))}


def similarity_to_recent(script: dict, eid: str = "", n: int = 15) -> tuple[float, str]:
    """Share of this script's 4-word phrases that already appeared in one of the last n episodes.
    YouTube demonetises channels whose videos differ only superficially; this keeps every episode genuinely new."""
    mine = _shingles(script)
    if not mine:
        return 0.0, ""
    best, twin = 0.0, ""
    for e in get_db().query("episodes", limit=n + 5):
        if e["id"] == eid or not e.get("script") or e.get("kind", "episode") != "episode" or e.get("edition_of"):
            continue
        other = _shingles(e["script"])
        if other:
            sim = len(mine & other) / len(mine)
            if sim > best:
                best, twin = sim, e["id"]
    return best, twin


# ---------------------------------------------------------------- schedule + publish
def free_slots(n: int = 6) -> list[str]:
    """Next free publishing times: every post_time on every post_day (3 a day by default), in the channel's zone."""
    s = app_settings()
    tz = ZoneInfo(s.get("timezone") or "UTC")
    days = set(s.get("post_days") or range(7))
    times = s.get("post_times") or [s.get("post_time") or "07:30"]
    times = sorted(times)[: max(1, int(s.get("episodes_per_day", len(times))))]
    db = get_db()
    taken = {(e.get("publish_at") or "")[:16] for e in db.query("episodes", in_={"status": ["approved", "publishing"]})}
    soon = datetime.now(timezone.utc).isoformat(timespec="seconds")
    taken |= {(e.get("published_at") or "")[:16] for e in db.query("episodes", eq={"status": "published"}, limit=200)
              if e.get("kind", "episode") == "episode" and (e.get("published_at") or "") > soon}   # uploaded, goes live later
    out, now = [], datetime.now(tz)
    for i in range(0, 120):
        base = now + timedelta(days=i)
        if base.weekday() not in days:
            continue
        for tm in times:
            hh, mm = (int(x) for x in tm.split(":"))
            slot = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if slot <= now + timedelta(hours=1):
                continue
            iso = slot.astimezone(timezone.utc).isoformat(timespec="seconds")
            if iso[:16] not in taken:
                out.append(iso)
            if len(out) >= n:
                return out
    return out


def slot_for(ep: dict) -> str:
    """Next free slot; bedtime episodes take the day's last posting time (closest to bedtime)."""
    slots = free_slots(9)
    if ep.get("category") == "bedtime" or "bedtime" in str((ep.get("meta") or {}).get("title", "")).lower():
        s = app_settings()
        tz = ZoneInfo(s.get("timezone") or "UTC")
        last = max(s.get("post_times") or ["16:00"])
        late = [x for x in slots if datetime.fromisoformat(x).astimezone(tz).strftime("%H:%M") == last]
        if late:
            return late[0]
    return slots[0]


def approve(eid: str, publish_at: str | None) -> dict:
    db = get_db()
    ep = db.get("episodes", eid)
    if not ep or not ep.get("video_url"):
        raise ValueError("Episode has no rendered video yet")
    when = publish_at or slot_for(ep)
    ep = db.update("episodes", eid, {"status": "approved", "publish_at": when})
    log(f"Approved — publishes {when}", ep=eid)
    return ep


BINGE = {   # every video also lands in one of these, so a child who finishes one gets the next on autoplay
    "episode": ("🐰 All Hoppy Hop Hop Episodes | Songs, Stories & Learning for Kids",
                "Every Hoppy Hop Hop cartoon in one place: songs, bedtime stories, counting, colours, animals and more "
                "for toddlers and preschoolers. Press play and let Hoppy keep the fun going!"),
    "short": ("🎵 Hoppy Hop Hop Shorts | Quick Sing-Alongs for Kids",
              "Short, happy sing-along clips from Hoppy Hop Hop for toddlers and preschoolers."),
}


def publish(eid: str, force: bool = False) -> dict:
    db = get_db()
    s = app_settings()
    if s.get("kill_switch"):
        raise RuntimeError("Kill switch is on: nothing is published")
    ep = db.claim("episodes", eid, ["approved"] + (["review"] if force else []), {"status": "publishing"})
    if not ep:
        return db.get("episodes", eid)
    from .publish import youtube
    local = None
    try:
        meta = ep.get("meta") or {}
        local = storage.fetch(ep["video_url"])
        thumb = storage.fetch(ep["thumb_url"]) if ep.get("thumb_url") else None
        if thumb:
            thumb = thumb.rename(thumb.with_suffix(".jpg"))
        lang = ep.get("language", "en")
        rt = (s.get("edition_channels") or {}).get(lang, "") if lang != s.get("language", "en") else ""
        from .kids import feedback
        privacy, when = s.get("youtube_privacy", "public"), None
        slot = _parse(ep.get("publish_at"))
        if privacy == "public" and slot and slot > datetime.now(timezone.utc) + timedelta(minutes=20):
            # uploaded early as a scheduled video: YouTube itself makes it public exactly at the slot
            privacy, when = "private", slot.isoformat(timespec="seconds").replace("+00:00", "Z")
        desc = meta.get("description", "") if ep.get("kind") == "short" else feedback.with_link(meta.get("description", ""), ep["id"])
        res = youtube.upload(local, meta.get("title", ep["topic"]), desc, meta.get("tags", []),
                             privacy, thumb, lang.split("-")[0], meta.get("localizations"),
                             rt, meta.get("category_id", "27"), made_for_kids=True,
                             synthetic=bool(s.get("ai_disclosure")), short=ep.get("kind") == "short", publish_at=when)
        if when:
            res = {**res, "privacy": "public", "scheduled_for": when}
        ep = db.update("episodes", eid, {"status": "published", "youtube": res, "error": None,
                                         "published_at": slot.isoformat(timespec="seconds") if when else now_iso()})
        log(f"Uploaded; YouTube makes it public at {when}: {res['url']}" if when else f"Published on YouTube: {res['url']}", ep=eid)
        if s.get("series_playlists", True):
            # the series playlist + one binge playlist (all episodes / all Shorts): autoplay keeps kids watching
            lists = [(meta["playlist"], f"{meta['playlist']} — every episode in order.")] \
                if meta.get("playlist") and ep.get("kind") != "short" else []
            lists.append(BINGE["short" if ep.get("kind") == "short" else "episode"])
            for title, about in lists:
                try:
                    youtube.add_to_playlist(youtube.ensure_playlist(title, about, rt), res["id"], rt)
                except Exception as e:  # noqa: BLE001
                    log(f"Playlist add failed ({title}): {e}", "warn", eid)
        if ep.get("kind", "episode") == "episode" and s.get("shorts_from_episodes", True):
            try:
                make_short(eid)
            except Exception as e:  # noqa: BLE001
                log(f"Short not made: {e}", "warn", eid)
        return ep
    except Exception as e:  # noqa: BLE001
        log(f"Publish failed: {e}", "error", eid)
        return db.update("episodes", eid, {"status": "approved", "error": f"Publish failed: {str(e)[:300]}",
                                            "publish_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec="seconds")})
    finally:
        if local and str(local).startswith(str(config.WORK_DIR)):
            Path(local).unlink(missing_ok=True)


PREUPLOAD_HOURS = 12      # upload this far ahead as a scheduled video, so it goes live on time whatever the runners do


def _parse(iso: str | None) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def publish_due() -> list[str]:
    s = app_settings()
    if s.get("kill_switch"):
        return []
    # daily cap per slot day (published_at holds the go-live time, so early uploads count for their own day)
    per_day: dict[str, int] = {}
    for e in get_db().query("episodes", eq={"status": "published"}, limit=100):
        d = (e.get("published_at") or "")[:10]
        per_day[d] = per_day.get(d, 0) + 1
    cap = int(s.get("max_posts_per_day", 2)) + 3                          # shorts ride along (+3)
    out = []
    ahead = (datetime.now(timezone.utc) + timedelta(hours=PREUPLOAD_HOURS)).isoformat(timespec="seconds")
    for ep in get_db().query("episodes", eq={"status": "approved"}, lte={"publish_at": ahead}, order="publish_at", desc=False):
        day = (ep.get("publish_at") or "")[:10]
        if per_day.get(day, 0) >= cap:
            continue
        publish(ep["id"])
        out.append(ep["id"])
        per_day[day] = per_day.get(day, 0) + 1
    if out:
        try:                                   # uploaded videos no longer need their full copy here
            from . import janitor
            janitor.cleanup()
        except Exception as e:  # noqa: BLE001
            log(f"Storage cleanup skipped: {e}", "warn")
    return out


# ---------------------------------------------------------------- growth: shorts, compilations, editions
SHORT_GAP = timedelta(minutes=60)    # no two videos go live closer than this: each gets its own first viewers


def short_slot(at: datetime) -> str:
    """`at`, or the next half hour after it with no other video (Short or episode) within SHORT_GAP."""
    db = get_db()
    used = [_parse(e.get("publish_at")) for e in db.query("episodes", in_={"status": ["approved", "publishing"]})]
    used += [_parse(e.get("published_at")) for e in db.query("episodes", eq={"status": "published"}, limit=200)]
    used = [u for u in used if u]
    at = at.astimezone(timezone.utc).replace(second=0, microsecond=0)
    while any(abs(at - u) < SHORT_GAP for u in used):
        at += timedelta(minutes=30)
    return at.isoformat(timespec="seconds")


def make_short(parent_id: str) -> dict:
    """The episode's song (or its liveliest segment) as a vertical Short that links viewers to the channel."""
    from .render import episode as epr
    db = get_db()
    p = db.get("episodes", parent_id)
    if not p or not p.get("video_url"):
        raise ValueError("Parent episode has no video")
    songs = p.get("song_regions") or []
    if songs:
        start, end = songs[0]["start"] - 1.0, songs[0]["end"]
    else:
        seg = next((g for g in p.get("timeline", []) if g["kind"] in ("movement", "game", "learn")), None) or {"start": 30, "end": 85}
        start, end = seg["start"], seg["end"]
    end = min(end, start + 58)
    work = config.WORK_DIR / f"short-{parent_id}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        src = storage.fetch(p["video_url"])
        out = epr.cut_short(src, max(0, start), end, work / "short.mp4", p["meta"]["title"])
        url = storage.put(out, f"{parent_id}/short-{int(time.time())}.mp4", "video/mp4")
        m = p.get("meta") or {}
        cat = categories.get(p["category"])
        title = f"{(p['script'] or {}).get('title_idea') or p['topic']} 🎵 Sing Along! #shorts"[:100]
        desc = (f"Sing along with Pip, Mimi and friends! The full {int((p.get('duration') or 600) // 60)}-minute episode "
                f"is on our channel.\n\n{(m.get('description') or '').split(chr(10))[0]}\n\n#kidssongs #shorts #{cat['id']}")
        ep = db.insert("episodes", {
            "kind": "short", "parent_id": parent_id, "status": "review", "category": p["category"], "topic": p["topic"],
            "age_band": p["age_band"], "language": p.get("language", "en"), "script": p.get("script"),
            "meta": {"title": title, "description": desc, "tags": (m.get("tags") or [])[:10] + ["shorts"],
                     "category_id": "10" if songs else m.get("category_id", "27")},
            "video_url": url, "thumb_url": p.get("thumb_url"), "duration": round(end - start, 1), "timeline": [],
            "safety": p.get("safety"), "critic": p.get("critic"), "editions": {},
            "qa": {"ok": True, "checks": [{"name": "Cut from approved episode", "ok": True, "detail": parent_id}]}})
        log(f"Short cut from '{p['topic']}' ({end - start:.0f}s)", ep=ep["id"])
        if app_settings().get("autopilot") or p.get("status") in ("published", "approved"):
            at = max(datetime.now(timezone.utc), _parse(p.get("publish_at")) or datetime.now(timezone.utc)) + timedelta(hours=26)
            ep = db.update("episodes", ep["id"], {"status": "approved", "publish_at": short_slot(at)})
        return ep
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make_compilation(minutes: int | None = None) -> dict:
    """Best published episodes back to back (parents leave long videos playing = watch time)."""
    from .render import episode as epr
    s = app_settings()
    target = (minutes or int(s.get("compilation_minutes", 45))) * 60
    db = get_db()
    eps = [e for e in db.query("episodes", eq={"status": "published"}, limit=200)
           if e.get("kind", "episode") == "episode" and e.get("video_url") and not e.get("archived")]
    if len(eps) < 2:
        raise ValueError("Need at least 2 published episodes for a compilation")
    eps.sort(key=lambda e: ((e.get("stats") or {}).get("avg_pct", 0), (e.get("stats") or {}).get("views", 0)), reverse=True)
    picked, total = [], 0.0
    for e in eps:
        if total >= target:
            break
        picked.append(e)
        total += e.get("duration") or 600
    work = config.WORK_DIR / f"comp-{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        files = [storage.fetch(e["video_url"]) for e in picked]
        out = epr.compile_videos(files, work / "compilation.mp4")
        url = storage.put(out, f"compilations/{out.parent.name}.mp4", "video/mp4")
        name = s.get("channel_name", "Hoppy Hop Hop")
        rows, t = [], 0.0
        for e in picked:
            rows.append(f"{int(t) // 60}:{int(t) % 60:02d} {(e.get('meta') or {}).get('title', e['topic'])[:60]}")
            t += e.get("duration") or 600
        cats = sorted({categories.get(e["category"])["name"] for e in picked})[:3]
        title = f"{int(total // 60)} Minutes of Learning Songs & Stories for Kids | {', '.join(cats)} | {name}"[:100]
        desc = (f"{int(total // 60)} minutes of calm, happy learning with Pip, Mimi, Bo, Zuzu and Nana Owl.\n\n"
                f"👉 Grown-ups: subscribe to {name} for new episodes every week!\n\nEpisodes:\n" + "\n".join(rows))
        thumb_url = picked[0].get("thumb_url")
        ep = db.insert("episodes", {
            "kind": "compilation", "status": "review", "category": picked[0]["category"], "topic": title,
            "age_band": picked[0]["age_band"], "language": picked[0].get("language", "en"),
            "meta": {"title": title, "description": desc, "tags": ["kids songs", "learning videos for kids", "compilation",
                                                                   "toddler learning", "preschool", name],
                     "category_id": "27", "playlist": f"⭐ Long Videos | {name}"},
            "video_url": url, "thumb_url": thumb_url, "duration": round(total, 1), "parts": [e["id"] for e in picked],
            "timeline": [], "editions": {}, "safety": {"ok": True, "issues": []},
            "qa": {"ok": True, "checks": [{"name": "Built from published episodes", "ok": True, "detail": f"{len(picked)} episodes"}]}})
        log(f"Compilation ready: {len(picked)} episodes, {total / 60:.0f} min", ep=ep["id"])
        if s.get("autopilot"):
            ep = approve(ep["id"], None)
        return ep
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make_edition(eid: str, lang: str) -> dict:
    """A full dubbed copy: translate → native voices → render → its own episode row (kind 'episode', language lang)."""
    db = get_db()
    p = db.get("episodes", eid)
    if not p or not p.get("script"):
        raise ValueError("Episode has no script")
    if not has_ai():
        raise ValueError("Dubbed editions need an AI key (translation)")
    script = metamod.translate_script(p["script"], lang)
    ed = db.insert("episodes", {
        "kind": "episode", "edition_of": eid, "status": "scripted", "category": p["category"], "topic": p["topic"],
        "age_band": p["age_band"], "language": lang, "minutes": p.get("minutes", 12), "script": script,
        "critic": p.get("critic"), "safety": safety.check_episode({"script": script, "meta": {}}), "editions": {},
        "meta": {**(p.get("meta") or {}), **((p.get("meta") or {}).get("localizations", {}).get(lang) or {}), "localizations": {}},
        "why": f"Dubbed edition of {eid}"})
    eds = dict(p.get("editions") or {})
    eds[lang] = {"id": ed["id"], "status": "scripted"}
    db.update("episodes", eid, {"editions": eds})
    log(f"Dubbed {lang} edition queued", ep=ed["id"])
    return ed


# ---------------------------------------------------------------- analytics
def refresh_analytics() -> dict:
    from .publish import youtube
    db = get_db()
    pub = [e for e in db.query("episodes", eq={"status": "published"}, limit=500) if (e.get("youtube") or {}).get("id")]
    ids = [e["youtube"]["id"] for e in pub]
    if not ids:
        return {"updated": 0}
    stats = youtube.video_stats(ids)
    try:
        ret = youtube.retention(ids)
    except Exception:  # noqa: BLE001 - analytics scope may be missing
        ret = {}
    perf: dict = {}
    for e in pub:
        vid = e["youtube"]["id"]
        st = {**stats.get(vid, {}), **ret.get(vid, {})}
        if st:
            db.update("episodes", e["id"], {"stats": st})
        if e.get("kind", "episode") == "episode" and "avg_pct" in st:
            p = perf.setdefault(e["category"], {"sum": 0.0, "n": 0})
            p["sum"] += st["avg_pct"]
            p["n"] += 1
    db.set_setting("category_perf", {k: {"avg_pct": v["sum"] / v["n"], "n": v["n"]} for k, v in perf.items()})
    # reinforcement: re-score the variants, then learn which segment kinds hold children (retention curves)
    from .kids import optimizer
    learned = optimizer.learn()
    curves = {}
    recent = [e for e in db.query("episodes", eq={"status": "published"}, limit=40)
              if e.get("kind", "episode") == "episode" and (e.get("youtube") or {}).get("id") and e.get("timeline")][:20]
    for e in recent:
        try:
            curves[e["youtube"]["id"]] = youtube.retention_curve(e["youtube"]["id"])
        except Exception:  # noqa: BLE001 - needs the analytics scope; fine to skip
            break
    segs = optimizer.learn_segments(curves, recent) if curves else {}
    return {"updated": len(stats), "optimizer_episodes": learned.get("episodes"), "segments": segs}


# ---------------------------------------------------------------- the heartbeat
def process(eid: str) -> dict:
    ep = get_db().get("episodes", eid)
    if not ep:
        return {}
    if ep["status"] == "planned":
        ep = write(eid)
    if ep and ep.get("status") == "scripted":
        ep = render(eid)
    return ep


def _recover():
    """Rows stuck in an active state for 90+ min (worker died) go back one step."""
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat(timespec="seconds")
    for e in db.query("episodes", in_={"status": list(ACTIVE)}, lte={"updated_at": cutoff}):
        back = {"writing": "planned", "rendering": "scripted", "publishing": "approved"}[e["status"]]
        db.update("episodes", e["id"], {"status": back})
        log(f"Recovered stuck episode ({e['status']} → {back})", "warn", e["id"])


def _keep_full():
    s = app_settings()
    if not s.get("auto_generate", True):
        return
    db = get_db()
    pending = [e for e in db.query("episodes", in_={"status": ["planned", "writing", "scripted", "rendering", "review", "approved"]})
               if e.get("kind", "episode") == "episode" and e.get("language", "en") == s.get("language", "en")]
    want = int(s.get("episodes_per_day", 3)) * 2 + 1          # two days of episodes in the pipe
    if not has_ai():
        want = 1                      # without an AI writer every plan is the same demo: keep just one, don't churn
    room = min(3, max(0, want - len(pending)))                 # at most 3 new plans per heartbeat
    if room:
        try:                                   # every waiting episode holds its full video: plan only what fits
            from . import janitor
            u = janitor.usage()
            if u["pct"] is not None and u["pct"] >= 100 * janitor.SOFT:
                janitor.cleanup()              # published videos are on YouTube: free their copies first
                u = janitor.usage()
            if u["pct"] is not None:
                fits = int((u["limit_mb"] * 0.9 - u["used_mb"]) // janitor.EPISODE_MB)
                if fits < room:
                    log(f"Storage {u['used_mb']:.0f} of {u['limit_mb']} MB: planning {max(0, fits)} of {room} new episodes", "warn")
                    room = max(0, fits)
        except Exception:  # noqa: BLE001
            pass
    if room and s.get("book_series") and has_ai():
        from .kids import series
        book_want = min(want, int(s.get("book_series_per_day", 1)) * 2)
        books = max(1, room // 2)              # the book series never takes every new slot: keep the topic mix
        for _ in range(min(books, max(0, book_want - series.pending_count(pending)))):
            try:
                series.plan_one()
                room -= 1
            except Exception as e:  # noqa: BLE001  (Gutenberg unreachable etc.: plan a normal episode instead)
                log(f"Book series: could not plan the next story ({e})", "warn")
                break
    for _ in range(room):
        create(why="Autopilot: keeping two days of episodes ready")


def _weekly_compilation():
    s = app_settings()
    if not s.get("compilation_weekly", True):
        return
    now = datetime.now(ZoneInfo(s.get("timezone") or "UTC"))
    if now.weekday() != int(s.get("compilation_weekday", 5)):
        return
    db = get_db()
    key = f"compilation_{now.date().isoformat()}"
    if db.get_setting(key):
        return
    db.set_setting(key, True)
    try:
        make_compilation()
    except ValueError as e:
        log(f"No compilation this week: {e}", "info")


def tick(render_work: bool = True, budget_s: int = 2700) -> dict:
    """One heartbeat. Safe to run from several places: every state change is an atomic claim."""
    if not _lock.acquire(blocking=False):
        return {"skipped": "busy"}
    t0 = time.time()
    out: dict = {"published": [], "processed": []}
    try:
        _recover()
        from . import automation
        out["retried"] = automation.auto_retry()
        out["published"] = publish_due()
        _keep_full()
        if render_work:
            db = get_db()
            for e in db.query("episodes", in_={"status": ["planned", "scripted"]}, order="created_at", desc=False, limit=10):
                if time.time() - t0 > budget_s:
                    break
                process(e["id"])
                out["processed"].append(e["id"])
            out["approved"] = automation.auto_approve()
            out["auto_review"] = automation.auto_review()
            out["published"] += publish_due()
        db = get_db()
        day = datetime.now(timezone.utc).date().isoformat()
        if db.get_setting("analytics_day") != day:
            db.set_setting("analytics_day", day)
            try:
                out["analytics"] = refresh_analytics()
            except Exception as e:  # noqa: BLE001
                out["analytics"] = f"skipped: {str(e)[:120]}"
            try:
                from .kids import growth
                out["timezone"] = growth.tune_timezone()
            except Exception as e:  # noqa: BLE001
                out["timezone"] = f"skipped: {str(e)[:120]}"
            try:
                from . import janitor
                out["storage"] = janitor.cleanup()
            except Exception as e:  # noqa: BLE001
                out["storage"] = f"skipped: {str(e)[:120]}"
            try:
                db.prune()
            except Exception:  # noqa: BLE001
                pass
            try:                                   # daily: what are children watching / parents searching now?
                from .kids import trends
                out["trends"] = trends.scan(lambda m: log(m)).get("ideas")
            except Exception as e:  # noqa: BLE001
                out["trends"] = f"skipped: {str(e)[:120]}"
        if render_work:
            _weekly_compilation()
        return out
    finally:
        _lock.release()


def current() -> dict:
    return dict(_current)


def overview_warnings() -> list[str]:
    s = app_settings()
    w = []
    if not has_ai():
        w.append("No AI key: episodes use the built-in template. Add a free Gemini or Groq key in Settings → Keys.")
    if not (secret("YT_CLIENT_ID") and secret("YT_REFRESH_TOKEN")):
        w.append("YouTube is not connected yet (Channel → Connect YouTube).")
    if s.get("kill_switch"):
        w.append("Kill switch is ON — nothing will be published.")
    if not s.get("made_for_kids", True):
        w.append("made_for_kids is off — content for children must be declared made for kids (COPPA).")
    if config.IS_PROD and not config.SUPABASE_URL:
        w.append("Production without Supabase: videos are stored on local disk.")
    return w
