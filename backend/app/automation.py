"""Full auto mode: the studio runs the channel on its own, safely.

One switch (Settings `full_auto`, or the Home page) turns on: planning (keep two days of episodes ready), writing,
rendering, quality gates, approval into the next posting slot, publishing, Shorts, weekly compilations, analytics
and the daily trend scan. Every heartbeat (pipeline.tick, every 5 minutes on this server or on the render farm):

  1. recover stuck work          (pipeline._recover)
  2. retry failed episodes       auto_retry(): up to `max_retries` times, 30 min apart
  3. plan / write / render       (pipeline._keep_full + process)
  4. approve what passes         auto_approve(): only if EVERY gate passes, else it stays in Review with the reason
  4b. fix what doesn't           auto_review(): re-render (QA / no video) or rewrite (low score / demo script) up to
                                 MAX_AUTO_FIXES times; still failing, or blocked by the safety gate → rejected, and the
                                 planner makes a replacement. Channel-wide blockers (YouTube, kill switch) just wait.
  5. publish what is due         (pipeline.publish_due — respects max_posts_per_day and the kill switch)

Gates for publishing without a human (children's content, so strict):
  real AI-written script (never the built-in demo) · safety gate passed · QA passed (length, flash safety, voices,
  resolution) · child-psychology score >= quality_bar · YouTube connected · kill switch off · made for kids on.
"""
from __future__ import annotations

import shutil
import time
from datetime import datetime, timedelta, timezone

from . import config
from .db import get_db, now_iso
from .settings import app_settings, save_app_settings, secret

RETRY_AFTER_MIN = 30


def _yt() -> bool:
    return bool(secret("YT_CLIENT_ID") and secret("YT_CLIENT_SECRET") and secret("YT_REFRESH_TOKEN"))


def gates(ep: dict, s: dict | None = None) -> list[str]:
    """Why this episode can NOT be published automatically ([] = it can)."""
    s = s or app_settings()
    why = []
    script = ep.get("script") or {}
    if script.get("writer") != "ai":
        why.append("built-in demo script (add an AI key for real episodes)")
    if not (ep.get("safety") or {}).get("ok", False):
        why.append("safety gate did not pass")
    qa = ep.get("qa") or {}
    if not qa.get("ok"):
        bad = [c["name"] for c in qa.get("checks", []) if not c.get("ok")]
        why.append("QA: " + (", ".join(bad) if bad else "not run"))
    score = (ep.get("critic") or {}).get("score") or 0
    if score < float(s.get("quality_bar", 7.5)):
        why.append(f"psychology score {score} < {s.get('quality_bar', 7.5)}")
    if not ep.get("video_url"):
        why.append("no video yet")
    if not _yt():
        why.append("YouTube not connected")
    if s.get("kill_switch"):
        why.append("kill switch is on")
    if not s.get("made_for_kids", True):
        why.append("made-for-kids is off")
    return why


def auto_approve(log=print) -> list[str]:
    """Review → approved (next free slot) for episodes that pass every gate. Others get the reason recorded."""
    s = app_settings()
    if not (s.get("full_auto") or s.get("autopilot")):
        return []
    from .pipeline import approve
    db = get_db()
    done = []
    for ep in db.query("episodes", eq={"status": "review"}, order="created_at", desc=False, limit=20):
        why = gates(ep, s)
        if why:
            if ep.get("auto_hold") != why:
                db.update("episodes", ep["id"], {"auto_hold": why})
            continue
        approve(ep["id"], None)
        db.update("episodes", ep["id"], {"auto_hold": []})
        db.log("Auto: approved (all gates passed) for the next posting slot", episode_id=ep["id"])
        done.append(ep["id"])
    return done


MAX_AUTO_FIXES = 2
CHANNEL_BLOCKERS = ("YouTube not connected", "kill switch is on", "made-for-kids is off")


def _too_short(ep: dict) -> bool:
    return any(c["name"].startswith("Length") and not c.get("ok") and "min (target" in c.get("detail", "")
               and float(c["detail"].split(" min")[0]) < float(c["detail"].split("target ")[1].split(",")[0])
               for c in (ep.get("qa") or {}).get("checks", []))


def auto_review(log=print) -> dict:
    """Nobody has to open Review: held episodes are fixed automatically, or replaced if they can't be."""
    s = app_settings()
    out: dict = {"rerender": [], "rewrite": [], "rejected": []}
    if not s.get("full_auto"):
        return out
    from .pipeline import has_ai
    db = get_db()

    def reject(ep: dict, why: str) -> None:
        db.update("episodes", ep["id"], {"status": "rejected", "publish_at": None, "error": why[:300]})
        db.log(f"Auto: rejected ({why[:200]}); a new episode will be planned instead", "warn", ep["id"])
        out["rejected"].append(ep["id"])

    for ep in db.query("episodes", eq={"status": "review"}, order="created_at", desc=False, limit=20):
        why = gates(ep, s)
        if not why or any(w in CHANNEL_BLOCKERS for w in why):
            continue                                   # approvable, or waiting on the channel (not the episode)
        n = int(ep.get("auto_fixes") or 0)
        if n >= MAX_AUTO_FIXES:
            reject(ep, f"still not good enough after {n} automatic fixes: " + "; ".join(why))
            continue
        content = [w for w in why if w.startswith(("psychology score", "built-in demo"))]
        short = _too_short(ep)
        if (content or short) and not has_ai():
            continue                                   # can't write without an AI writer: wait for a key
        patch = {"auto_fixes": n + 1, "auto_hold": why, "progress": {"stage": "queued (auto fix)", "pct": 0}}
        if content:                                    # weak script → write it again
            patch["status"], how = "planned", "rewriting"
        elif short:                                    # good script, rendered short → add lines, render again
            from .kids import writer
            try:
                script = writer.lengthen(ep["script"], float(ep.get("minutes") or s.get("target_minutes") or 12))
            except Exception as e:  # noqa: BLE001  (AI busy: try again next heartbeat, doesn't use up a fix)
                db.log(f"Auto review: could not lengthen yet ({str(e)[:120]})", "warn", ep["id"])
                continue
            before = writer.template_seconds(ep["script"]["segments"], ep.get("age_band") or "preschool")
            if writer.template_seconds(script["segments"], ep.get("age_band") or "preschool") < before + 30:
                continue                               # AI busy, nothing added: try next heartbeat, fix not used up
            patch.update(status="scripted", script=script)
            how = "lengthening the script and re-rendering"
        else:                                          # other QA issue / no video → render again
            patch["status"], how = "scripted", "re-rendering"
        db.update("episodes", ep["id"], patch)
        db.log(f"Auto review ({n + 1}/{MAX_AUTO_FIXES}): {how} — " + "; ".join(why), "warn", ep["id"])
        out["rewrite" if content else "rerender"].append(ep["id"])

    for ep in db.query("episodes", eq={"status": "failed"}, limit=50):   # dead ends: clear them so the pipe refills
        err = str(ep.get("error") or "")
        if err.startswith("Safety gate"):
            reject(ep, err)
        elif int(ep.get("retries") or 0) >= int(s.get("max_retries", 2)):
            reject(ep, f"failed after {ep.get('retries')} retries: {err[:150]}")
    return out


def auto_retry() -> list[str]:
    """Failed episodes go round again (max_retries times, 30 minutes apart) — from the step that failed."""
    s = app_settings()
    if not (s.get("full_auto") or s.get("auto_retry", True)):
        return []
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=RETRY_AFTER_MIN)).isoformat(timespec="seconds")
    out = []
    for ep in db.query("episodes", eq={"status": "failed"}, lte={"updated_at": cutoff}, limit=20):
        n = int(ep.get("retries") or 0)
        if n >= int(s.get("max_retries", 2)):
            continue
        err = str(ep.get("error") or "")
        if err.startswith("Safety gate"):
            continue                                     # a blocked script is rewritten only by a human decision
        back = "scripted" if ep.get("script") and not err.startswith("Writing") else "planned"
        db.update("episodes", ep["id"], {"status": back, "retries": n + 1, "error": None,
                                         "progress": {"stage": "queued (retry)", "pct": 0}})
        db.log(f"Auto: retrying ({n + 1}/{s.get('max_retries', 2)}) from '{back}' after: {err[:120]}", "warn", ep["id"])
        out.append(ep["id"])
    return out


def record_tick(result: dict, seconds: float) -> None:
    try:
        get_db().set_setting("automation_last", {"at": now_iso(), "seconds": round(seconds, 1),
                                                 "result": {k: (v if not isinstance(v, list) else len(v))
                                                            for k, v in (result or {}).items()}})
    except Exception:  # noqa: BLE001
        pass


def checklist() -> list[dict]:
    from .pipeline import has_ai
    from .render import three_d
    s = app_settings()
    free_gb = shutil.disk_usage(config.DATA_DIR).free / 1e9
    style = s.get("art_style", "auto")
    sched = config.INTERNAL_SCHEDULER == "1" or config.WORKER_MODE == "github" or bool(config.CRON_SECRET)
    return [
        {"id": "ai", "title": "AI writer key", "ok": has_ai(), "need": True,
         "detail": "Gemini or Groq (free) in Settings → Keys. Without it only demo episodes are made, and demos are never auto-published."},
        {"id": "youtube", "title": "YouTube connected", "ok": _yt(), "need": True,
         "detail": "Client ID + secret in Keys, then Channel → Connect YouTube."},
        {"id": "kill", "title": "Kill switch off", "ok": not s.get("kill_switch"), "need": True,
         "detail": "Settings → kill switch. While on, nothing is published."},
        {"id": "heartbeat", "title": "Heartbeat running", "ok": sched, "need": True,
         "detail": "This server ticks every 5 minutes (INTERNAL_SCHEDULER=1), or the GitHub render farm / a cron calls /api/cron/tick."},
        {"id": "renderer", "title": "Renderer ready", "ok": style != "toy3d" or three_d.available(), "need": True,
         "detail": "The 3D cartoon look needs Blender in backend/tools/blender; other looks need nothing."},
        {"id": "disk", "title": "Disk space", "ok": free_gb > 5, "need": False, "detail": f"{free_gb:.0f} GB free (each episode ~0.2-0.5 GB while rendering)."},
        {"id": "kids", "title": "Made for kids", "ok": bool(s.get("made_for_kids", True)), "need": True,
         "detail": "Locked on (COPPA)."},
    ]


def status() -> dict:
    from .pipeline import free_slots
    s = app_settings()
    db = get_db()
    rows = db.query("episodes", limit=300)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    today = datetime.now(timezone.utc).date().isoformat()
    published_today = sum(1 for r in rows if r["status"] == "published" and (r.get("published_at") or "").startswith(today))
    held = [{"id": r["id"], "title": (r.get("meta") or {}).get("title") or r.get("topic"), "why": r.get("auto_hold") or gates(r, s)}
            for r in rows if r["status"] == "review"][:10]
    actions = [e for e in db.query("events", limit=200) if str(e.get("msg", "")).startswith(("Auto:", "Autopilot", "Planned:"))][:12]
    cl = checklist()
    return {"enabled": bool(s.get("full_auto")), "ready": all(c["ok"] for c in cl if c["need"]),
            "checklist": cl, "counts": counts, "published_today": published_today,
            "max_per_day": int(s.get("max_posts_per_day", 3)), "episodes_per_day": int(s.get("episodes_per_day", 3)),
            "next_slots": free_slots(4), "held": held, "last_tick": db.get_setting("automation_last"),
            "actions": [{"at": a["created_at"], "msg": a["msg"][:200], "episode_id": a.get("episode_id"),
                         "level": a.get("level")} for a in actions],
            "heartbeat_minutes": 5}


def enable(on: bool) -> dict:
    patch = {"full_auto": bool(on)}
    if on:
        patch.update(autopilot=True, auto_generate=True, auto_retry=True, shorts_from_episodes=True,
                     compilation_weekly=True, optimizer=True)
    else:
        patch.update(autopilot=False)
    save_app_settings(patch)
    get_db().log("Full auto mode " + ("ON: the studio plans, makes, checks and publishes on its own (strict gates)"
                                      if on else "OFF: episodes wait in Review for you"))
    return status()


def heartbeat() -> dict:
    """Run one full cycle now (what the 5-minute heartbeat does)."""
    from .pipeline import tick
    t = time.time()
    res = tick(True, 2700)
    record_tick(res, time.time() - t)
    return res
