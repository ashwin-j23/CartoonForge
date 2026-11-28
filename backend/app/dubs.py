"""The dubbed channel: one picture, many languages.

Hoppy Hop Hop (the main channel) is English only. Each finished English episode is dubbed into every language in
Settings → editions and uploaded to a second YouTube channel (Channel page → Connect dubbed channel). Nothing is drawn
again: the episode's own picture is reused, only the voices are new, fitted line by line into the original's timing.
The state lives on the English episode: editions[lang] = {status, youtube, publish_at, error, tries}.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, storage
from .db import get_db
from .kids import languages, meta as metamod, safety
from .settings import app_settings, secret

TOKEN = "YT_DUB_REFRESH_TOKEN"
LEAD_DAYS = 3          # an approved episode is dubbed this many days before it goes live in English
MAX_TRIES = 3
LIMIT_PAUSE_H = 24     # YouTube's daily upload cap for the channel was hit: no dubbing until it resets
TIGHT_MAX = .12        # more lines than this that don't fit their time: the dub is not good enough to publish


def token() -> str:
    return secret(TOKEN)


def wanted(ep: dict, s: dict | None = None) -> list[str]:
    """Languages this episode still has to be dubbed into."""
    if ep.get("kind", "episode") not in (None, "episode") or ep.get("language", "en") != "en" or ep.get("edition_of"):
        return []
    s = s or app_settings()
    eds = ep.get("editions") or {}
    langs = list(s.get("editions") or []) + [lg for lg, e in eds.items() if e.get("status") == "planned"]
    out = []
    for lg in dict.fromkeys(langs):
        e = eds.get(lg) or {}
        if lg == "en" or lg not in languages.LANGS or e.get("status") == "published" or int(e.get("tries") or 0) >= MAX_TRIES:
            continue
        out.append(lg)
    return out


def keep_picture(ep: dict) -> bool:
    """The full-quality picture is still needed (the cleanup must not shrink it yet): for at most 10 days."""
    if not token() or ep.get("archived") or not wanted(ep):
        return False
    at = _parse(ep.get("rendered_at"))
    return bool(at and datetime.now(timezone.utc) - at < timedelta(days=10))


def _parse(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def live_at(ep: dict) -> datetime | None:
    return _parse(ep.get("published_at") if ep.get("status") == "published" else ep.get("publish_at"))


# ---------------------------------------------------------------- voices on the existing picture
def line_times(ep: dict, work: Path, rs: dict) -> dict:
    """When every line starts and ends in the finished picture. Older renders didn't store it: the English voices are
    recorded once more and each segment is scaled onto its stored start and end (they differ by ~0.2%)."""
    from .render import audio
    tl, script = ep.get("timeline") or [], ep["script"]
    if len(tl) != len(script["segments"]):
        raise ValueError("The script changed after the render: render the episode again before dubbing it")
    if all(len(g.get("lines") or []) == len(seg["scenes"]) for g, seg in zip(tl, script["segments"])):
        return {"segs": [g["start"] for g in tl], "lines": [g["lines"] for g in tl]}
    snd = audio.build(script, rs, work / "en.wav", config.RENDER_FPS, lambda m: None)
    lines = []
    for g, h in zip(tl, snd["segments"]):
        k = (g["end"] - g["start"]) / max(.1, h["end"] - h["start"])
        at = lambda x: round(g["start"] + (x - h["start"]) * k, 3)   # noqa: E731
        lines.append([[at(a), at(b), at(c), [at(r) for r in rv]] for a, b, c, rv in h["lines"]])
    return {"segs": [g["start"] for g in tl], "lines": lines}


def render(ep: dict, lang: str, picture: Path, work: Path, log=print) -> tuple[Path, dict]:
    """The dubbed video: the episode's picture (copied, not redrawn) with a new soundtrack. Returns (file, script)."""
    from .pipeline import palette_for
    from .render import audio
    s = app_settings()
    var = ep.get("variant") or {}
    rs = {**s, "_pace": var.get("pace") or s.get("pace"), "_palette": palette_for(ep, s)}
    times = line_times(ep, work, rs)
    secs = [[round(max(r[1] - r[0], .8), 1) for r in g] for g in times["lines"]]
    script = metamod.translate_script(ep["script"], lang, secs)
    gate = safety.check_episode({"script": script, "meta": {}})
    if not gate["ok"]:
        raise ValueError("Safety gate blocked the translation: " + "; ".join(
            f"{i['rule']}: {i['word']}" for i in gate["issues"] if i["level"] == "block")[:200])
    wav = work / f"{lang}.wav"
    snd = audio.build(script, {**rs, "_dub": times}, wav, config.RENDER_FPS, log)
    if "espeak" in snd["engines"]:
        raise RuntimeError(f"No natural {languages.name(lang)} voice was available")
    n = sum(len(g["scenes"]) for g in script["segments"])
    if len(snd["tight"]) > TIGHT_MAX * n:
        raise RuntimeError(f"{len(snd['tight'])} of {n} dubbed lines are too long for the picture")
    out = work / f"{lang}.mp4"
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-i", str(picture), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-af", "loudnorm=I=-15:TP=-1.5:LRA=11,apad", "-ar", "48000", "-ac", "2", "-c:a", "aac",
                    "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(out)], check=True)
    wav.unlink(missing_ok=True)
    return out, script


# ---------------------------------------------------------------- words around the video
def dub_meta(ep: dict, lang: str, script: dict | None = None) -> dict:
    """Title, description (with the chapters named in the dub's language) and tags for the dubbed channel."""
    m = ep.get("meta") or {}
    loc = (m.get("localizations") or {}).get(lang) or metamod.localize(m, [lang]).get(lang) or {}
    if not loc.get("title"):
        raise RuntimeError(f"Title not translated into {languages.name(lang)} (AI busy)")
    native = languages.LANGS[lang][1]
    name = channel_name()
    desc = re.sub(r"\S*youtube\.com/@\S+", "", loc.get("description") or "").replace("👉 \n", "\n").strip()
    main = app_settings().get("channel_name", "Hoppy Hop Hop")
    if name != main:                                        # 'subscribe to …' means this channel, not the English one
        desc = re.sub(rf"{re.escape(main)}(?! World)", name, desc, count=1)
    if script and len(ep.get("timeline") or []) == len(script["segments"]):
        ch = metamod.chapters([{**g, "title": seg["title"]} for g, seg in zip(ep["timeline"], script["segments"])])
        desc = re.sub(r"(?m)^\d+:\d\d .*(?:\n\d+:\d\d .*)+", lambda _: ch, desc, count=1) if ch else desc
    tags = [f"{native} cartoon", f"{languages.name(lang)} cartoon for kids", f"{languages.name(lang)} kids songs",
            f"{languages.name(lang)} stories for kids"] + list(m.get("tags") or [])
    return {"title": loc["title"][:100], "description": desc, "tags": tags, "playlist": f"{native} · {name}"}


def channel_name() -> str:
    """The dubbed channel's own name (from YouTube, cached by status()); the English name + ' World' until then."""
    db = get_db()
    ch = db.get_setting("dub_channel_cache") or {}
    if token() and time.time() - float(ch.get("t") or 0) > 6 * 3600:     # renamed on YouTube? read it again
        try:
            from .publish import youtube
            ch = {**youtube.channel_info(token()), "t": time.time()}
            db.set_setting("dub_channel_cache", ch)
        except Exception:  # noqa: BLE001
            pass
    return ch.get("title") or f"{app_settings().get('channel_name', 'Hoppy Hop Hop')} World"


def thumb(ep: dict, lang: str, out: Path) -> Path:
    """The episode's thumbnail without English words (the fonts can't draw every script; faces work everywhere)."""
    from .pipeline import palette_for
    from .render import episode as epr
    m = ep.get("meta") or {}
    var = ep.get("variant") or {}
    return epr.thumbnail(ep["script"], {**app_settings(), "_meta": m, "_thumb": var.get("thumb", "face"), "_style": "classic",
                                        "_palette": palette_for(ep, app_settings()), "_no_words": True}, out)


# ---------------------------------------------------------------- schedule
def next_slot(rows: list[dict], after: datetime) -> str:
    """The dubbed channel's next free time (dub_times every day), never before the English episode."""
    s = app_settings()
    tz = ZoneInfo(s.get("timezone") or "UTC")
    taken = {str((e or {}).get("publish_at"))[:16] for r in rows for e in (r.get("editions") or {}).values() if isinstance(e, dict)}
    start = max(after, datetime.now(timezone.utc)) + timedelta(hours=1)
    for d in range(200):
        for tm in sorted(s.get("dub_times") or ["09:00", "17:00"]):
            hh, mm = (int(x) for x in tm.split(":"))
            t = (start.astimezone(tz) + timedelta(days=d)).replace(hour=hh, minute=mm, second=0, microsecond=0).astimezone(timezone.utc)
            iso = t.isoformat(timespec="seconds")
            if t > start and iso[:16] not in taken:
                return iso
    raise RuntimeError("No free time on the dubbed channel")


def _save(eid: str, lang: str, patch: dict) -> dict:
    db = get_db()
    eds = dict(db.get("episodes", eid).get("editions") or {})
    eds[lang] = {**(eds.get(lang) or {}), **patch}
    db.update("episodes", eid, {"editions": eds})
    return eds[lang]


def make(eid: str, lang: str, picture: Path | None = None, log=print) -> dict:
    """Dub one episode into one language and upload it, scheduled, to the dubbed channel."""
    from .publish import youtube
    db = get_db()
    ep = db.get("episodes", eid)
    tries = int(((ep.get("editions") or {}).get(lang) or {}).get("tries") or 0) + 1
    _save(eid, lang, {"status": "rendering", "tries": tries, "error": None, "started": time.time()})
    work = config.WORK_DIR / f"dub-{eid}-{lang}"
    work.mkdir(parents=True, exist_ok=True)
    own = None
    try:
        if not token():
            raise RuntimeError("The dubbed channel is not connected")
        if picture is None:
            picture = own = storage.fetch(ep["video_url"])
        if _height(picture) < 720:
            raise RuntimeError("Only the small preview of this episode is left; render it again to dub it")
        video, script = render(ep, lang, picture, work, log)
        meta = dub_meta(ep, lang, script)
        th = thumb(ep, lang, work / "thumb.jpg")
        rows = db.query("episodes", in_={"status": ["approved", "published"]}, limit=500, light=True)
        when = next_slot(rows, live_at(ep) or datetime.now(timezone.utc))
        res = youtube.upload(video, meta["title"], meta["description"], meta["tags"], "private", th, lang, None, token(),
                             (ep.get("meta") or {}).get("category_id", "27"), made_for_kids=True,
                             synthetic=bool(app_settings().get("ai_disclosure")), publish_at=when.replace("+00:00", "Z"))
        ed = _save(eid, lang, {"status": "published", "youtube": res, "publish_at": when, "published_at": when, "error": None,
                               "title": meta["title"]})
        log(f"{languages.name(lang)} dub uploaded to the dubbed channel, public at {when}: {res['url']}")
        try:
            youtube.add_to_playlist(youtube.ensure_playlist(meta["playlist"], meta["playlist"], token()), res["id"], token())
        except Exception as e:  # noqa: BLE001  (a playlist is a bonus)
            log(f"Dub playlist: {str(e)[:120]}")
        return ed
    except Exception as e:  # noqa: BLE001
        if "exceeded the number of videos" in str(e):      # the channel's daily upload cap, not this dub's fault
            until = time.time() + LIMIT_PAUSE_H * 3600
            get_db().set_setting("dub_paused_until", until)
            log(f"{languages.name(lang)} dub waits: YouTube's daily upload limit for the dubbed channel was reached; "
                f"dubbing resumes in {LIMIT_PAUSE_H} h")
            return _save(eid, lang, {"status": "planned", "tries": tries - 1, "error": "Waiting: the dubbed channel's daily upload limit"})
        log(f"{languages.name(lang)} dub failed (try {tries} of {MAX_TRIES}): {str(e)[:250]}")
        return _save(eid, lang, {"status": "failed" if tries >= MAX_TRIES else "planned", "error": str(e)[:250]})
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if own and str(own).startswith(str(config.WORK_DIR)):
            Path(own).unlink(missing_ok=True)


def _height(p: Path) -> int:
    r = subprocess.run([config.FFMPEG, "-hide_banner", "-i", str(p)], capture_output=True, text=True)
    m = re.search(r"Video:.*?, \d{2,5}x(\d{2,5})", r.stderr)
    return int(m.group(1)) if m else 0


def paused() -> bool:
    """True while the dubbed channel waits for YouTube's daily upload limit to reset."""
    return time.time() < float(get_db().get_setting("dub_paused_until") or 0)


def due() -> list[tuple[str, str]]:
    """(episode, language) pairs to dub now: English episodes live, or going live within LEAD_DAYS, picture still here."""
    if not token():
        return []
    s = app_settings()
    soon = datetime.now(timezone.utc) + timedelta(days=LEAD_DAYS)
    rows = get_db().query("episodes", in_={"status": ["approved", "published"]}, limit=200, light=True)
    ready = [e for e in rows if e.get("video_url") and not e.get("archived") and wanted(e, s)
             and (live_at(e) or soon + timedelta(days=1)) <= soon]
    ready.sort(key=lambda e: str(live_at(e)))
    out = []
    for e in ready:
        for lg in wanted(e, s):
            ed = (e.get("editions") or {}).get(lg) or {}
            if ed.get("status") == "rendering" and time.time() - float(ed.get("started") or 0) < 3 * 3600:
                continue                                   # another worker is on it
            out.append((e["id"], lg))
    return out


def run(budget_s: float = 3600) -> list[str]:
    """Worker step: dub what is due until the time is used up."""
    from .pipeline import log
    t0, done = time.time(), []
    if app_settings().get("kill_switch") or paused():
        return done
    for eid, lang in due():
        if time.time() - t0 > budget_s or paused():
            break
        ed = make(eid, lang, log=lambda m, e=eid: log(m, ep=e) if "dub" in m.lower() else None)
        done.append(f"{eid}:{lang}:{ed['status']}")
    return done


_STATUS = {"published": "published", "rendering": "rendering", "failed": "failed", "planned": "scripted"}


def items(rows: list[dict], s: dict | None = None) -> list[dict]:
    """Every dub as its own row for the dashboard (channel 'world'), shaped like an episode summary.
    Languages still to come on approved/published episodes are listed as queued once the channel is connected."""
    s = s or app_settings()
    connected = bool(token())
    out = []
    for e in rows:
        if e.get("kind", "episode") not in (None, "episode") or e.get("edition_of"):
            continue
        eds = {lg: ed for lg, ed in (e.get("editions") or {}).items() if isinstance(ed, dict) and lg in languages.LANGS}
        todo = wanted(e, s) if connected and e.get("status") in ("approved", "published") and not e.get("archived") else []
        for lg in list(eds) + [lg for lg in todo if lg not in eds]:
            ed = eds.get(lg) or {}
            st = _STATUS.get(ed.get("status") or "planned", "scripted")
            m = e.get("meta") or {}
            out.append({
                "id": f"{e['id']}-{lg}", "episode_id": e["id"], "channel": "world", "kind": "dub", "lang": lg,
                "lang_name": languages.name(lg), "lang_native": languages.LANGS[lg][1],
                "title": ed.get("title") or m.get("title") or e.get("topic"), "topic": e.get("topic"),
                "status": st, "publish_at": ed.get("publish_at"), "published_at": ed.get("publish_at") if st == "published" else None,
                "created_at": e.get("created_at"), "category": e.get("category"), "age_band": e.get("age_band"),
                "duration": e.get("duration"), "thumb_url": e.get("thumb_url"), "youtube": ed.get("youtube"),
                "url": (ed.get("youtube") or {}).get("url"), "views": (ed.get("stats") or {}).get("views"),
                "likes": (ed.get("stats") or {}).get("likes"), "error": ed.get("error"), "tries": ed.get("tries"),
                "progress": {"stage": "dubbing", "pct": 50} if st == "rendering" else None,
                "parent_live_at": (live_at(e) or datetime.now(timezone.utc)).isoformat(timespec="seconds")})
    return out


def refresh_stats() -> int:
    """Views/likes of the dubbed channel's videos, saved on each episode's editions (daily, with the main analytics)."""
    from .publish import youtube
    if not token():
        return 0
    db = get_db()
    rows = [e for e in db.query("episodes", in_={"status": ["approved", "published"]}, limit=500, light=True)
            if any(isinstance(ed, dict) and (ed.get("youtube") or {}).get("id") for ed in (e.get("editions") or {}).values())]
    ids = [ed["youtube"]["id"] for e in rows for ed in e["editions"].values() if isinstance(ed, dict) and (ed.get("youtube") or {}).get("id")]
    stats = youtube.video_stats(ids, token()) if ids else {}
    n = 0
    for e in rows:
        eds = dict(e["editions"])
        for lg, ed in eds.items():
            vid = (ed.get("youtube") or {}).get("id") if isinstance(ed, dict) else None
            if vid and vid in stats:
                eds[lg] = {**ed, "stats": stats[vid]}
                n += 1
        db.update("episodes", e["id"], {"editions": eds})
    return n


def status() -> dict:
    """For the Channel page."""
    from .publish import youtube
    db = get_db()
    s = app_settings()
    out: dict = {"connected": False, "languages": s.get("editions") or [], "upcoming": [], "recent": [], "failed": [],
                 "paused_until": float(db.get_setting("dub_paused_until") or 0) if paused() else None}
    if token():
        ch = db.get_setting("dub_channel_cache") or {}
        if time.time() - ch.get("t", 0) > 3600:
            try:
                ch = {**youtube.channel_info(token()), "t": time.time()}
                db.set_setting("dub_channel_cache", ch)
            except Exception as e:  # noqa: BLE001
                ch = {"error": str(e)[:200]}
        out.update({k: v for k, v in ch.items() if k != "t"}, connected="id" in ch)
    now = datetime.now(timezone.utc).isoformat()
    for e in db.query("episodes", in_={"status": ["approved", "published"]}, limit=300, light=True):
        for lg, ed in (e.get("editions") or {}).items():
            if not isinstance(ed, dict):
                continue
            row = {"episode": e["id"], "lang": lg, "title": ed.get("title") or (e.get("meta") or {}).get("title"),
                   "status": ed.get("status"), "publish_at": ed.get("publish_at"), "url": (ed.get("youtube") or {}).get("url"),
                   "error": ed.get("error")}
            if ed.get("status") == "published":
                out["upcoming" if str(ed.get("publish_at")) > now else "recent"].append(row)
            elif ed.get("error"):
                out["failed"].append(row)
    out["upcoming"].sort(key=lambda r: str(r["publish_at"]))
    out["recent"].sort(key=lambda r: str(r["publish_at"]), reverse=True)
    out["recent"], out["failed"] = out["recent"][:10], out["failed"][:10]
    return out
