"""Storage housekeeping: keep the media bucket small (Supabase free plan = 1 GB) without losing anything needed.

Rules (run daily by the worker, or from the dashboard):
  1. Old renders: files an episode no longer points at (a re-render replaced them) are deleted.
  2. Published episodes: once on YouTube for KEEP_FULL_DAYS (its Short is made at publish time), the full-quality
     parts are deleted; the small 540p preview stays so the dashboard player keeps working.
  3. Rejected / failed episodes untouched for DEAD_DAYS: all their media is deleted.
  4. Published videos older than PREVIEW_DAYS: the preview goes too (the video lives on YouTube).
  5. Still over the soft limit: published episodes are slimmed (rule 2) oldest first, whatever their age.
  6. Still over: previews of videos already live on YouTube go too, oldest first.
Schedule (maintain(), every worker heartbeat): normal clean whenever storage is at HIGH (85%) or more, and a deep
clean every DEEP_EVERY_DAYS (3) days that also drops the previews of everything already live on YouTube.
Nothing waiting to be published is ever touched, and nothing uploaded in the last GRACE hours (a render in flight).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from . import config, storage
from .db import get_db

KEEP_FULL_DAYS = 3
DEAD_DAYS = 7
PREVIEW_DAYS = 45
GRACE_HOURS = 3
LIMIT_MB = int(config.env("STORAGE_LIMIT_MB", "1000"))      # Supabase free plan
SOFT = 0.5                                                  # aim for half the limit: new episodes need room to render
HIGH = 0.85                                                 # at or above this: clean right away
DEEP_EVERY_DAYS = 3                                         # deep clean this often whatever the level
EPISODE_MB = 260                                            # a full episode render waiting to be published
WAITING = ("planned", "writing", "scripted", "rendering", "review", "approved", "publishing")


def key_of(url: str | None) -> str:
    """Storage key of a media URL ('' if it isn't one of ours)."""
    if not url:
        return ""
    for marker in (f"/object/public/{config.SUPABASE_BUCKET}/", "/media/"):
        if marker in url:
            return url.split(marker, 1)[1].split("?", 1)[0]
    return ""


def _parse(iso: str | None) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def list_files() -> list[dict]:
    """[{path, size, created}] for every stored file."""
    out: list[dict] = []
    if storage._supabase():
        h = config.supabase_headers()

        def walk(prefix: str) -> None:
            off = 0
            while True:
                r = httpx.post(f"{config.SUPABASE_URL}/storage/v1/object/list/{config.SUPABASE_BUCKET}", headers=h,
                               json={"prefix": prefix, "limit": 1000, "offset": off}, timeout=60)
                r.raise_for_status()
                rows = r.json()
                for it in rows:
                    path = f"{prefix}/{it['name']}" if prefix else it["name"]
                    if it.get("id") is None:
                        walk(path)
                    else:
                        out.append({"path": path, "size": int((it.get("metadata") or {}).get("size") or 0),
                                    "created": _parse(it.get("created_at"))})
                if len(rows) < 1000:
                    return
                off += 1000
        walk("")
        return out
    root = config.MEDIA_DIR
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                st = p.stat()
                out.append({"path": str(p.relative_to(root)), "size": st.st_size,
                            "created": datetime.fromtimestamp(st.st_mtime, timezone.utc)})
    return out


def _delete(paths: list[str]) -> None:
    if not paths:
        return
    if storage._supabase():
        for i in range(0, len(paths), 100):
            r = httpx.request("DELETE", f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}",
                              json={"prefixes": paths[i:i + 100]}, timeout=60, headers=config.supabase_headers())
            r.raise_for_status()
        return
    for p in paths:
        (config.MEDIA_DIR / p).unlink(missing_ok=True)


def usage(files: list[dict] | None = None) -> dict:
    files = list_files() if files is None else files
    used = sum(f["size"] for f in files) / 1e6
    return {"files": len(files), "used_mb": round(used, 1), "limit_mb": LIMIT_MB,
            "pct": round(100 * used / LIMIT_MB, 1) if LIMIT_MB else None}


def _parts(files: list[dict], key: str) -> list[dict]:
    return [f for f in files if f["path"].startswith(key + ".part")]


def cleanup(dry: bool = False, deep: bool = False) -> dict:
    from . import dubs
    db = get_db()
    now = datetime.now(timezone.utc)
    files = list_files()
    before = usage(files)
    eps = db.query("episodes", limit=5000)
    gone: dict[str, str] = {}            # path -> reason
    patches: dict[str, dict] = {}

    def drop(fs: list[dict], why: str) -> None:
        for f in fs:
            gone.setdefault(f["path"], why)

    fresh = lambda f: f["created"] and now - f["created"] < timedelta(hours=GRACE_HOURS)   # noqa: E731

    # what episodes point at (a video key covers its parts + manifest)
    live: set[str] = set()
    for e in eps:
        for u in (e.get("video_url"), e.get("thumb_url")):
            if k := key_of(u):
                live.add(k)
    owned = lambda p: p in live or any(p.startswith(k + ".part") for k in live if k.endswith(".mp4"))   # noqa: E731

    # 1. old renders nobody points at (only in folders this app manages: <episode id>/ and compilations/)
    managed = lambda p: bool(re.fullmatch(r"[0-9a-f]{8,16}|compilations", p.split("/", 1)[0]))   # noqa: E731
    drop([f for f in files if managed(f["path"]) and "/" in f["path"] and not owned(f["path"]) and not fresh(f)],
         "old render")

    for e in eps:
        vk = key_of(e.get("video_url"))
        if e["status"] in WAITING or not vk:
            continue
        mine = [f for f in files if f["path"] == vk or f["path"].startswith(vk + ".part")]
        if e["status"] == "published":
            age = now - (_parse(e.get("published_at")) or now)
            # 4. long-published: drop even the preview (it lives on YouTube)
            if age > timedelta(days=PREVIEW_DAYS):
                drop(mine, "published long ago")
                patches[e["id"]] = {"video_url": None, "archived": True}
            # 2. published a few days: keep only the small preview
            elif age > timedelta(days=KEEP_FULL_DAYS) and _parts(files, vk) and not dubs.keep_picture(e):
                drop(_parts(files, vk), "published: full copy is on YouTube")
                patches[e["id"]] = {"archived": True}
        elif e["status"] in ("rejected", "failed"):
            idle = now - (_parse(e.get("updated_at")) or now)
            if idle > timedelta(days=DEAD_DAYS):
                tk = key_of(e.get("thumb_url"))
                drop([f for f in files if f["path"] == tk] + mine, f"{e['status']} for {DEAD_DAYS}+ days")
                patches[e["id"]] = {"video_url": None, "thumb_url": None}

    # 5. still too big: slim published episodes oldest first
    left = lambda: sum(f["size"] for f in files if f["path"] not in gone) / 1e6   # noqa: E731
    if deep or left() > LIMIT_MB * SOFT:
        pub = sorted([e for e in eps if e["status"] == "published" and key_of(e.get("video_url"))],
                     key=lambda e: e.get("published_at") or "")
        for e in pub:
            if not deep and left() <= LIMIT_MB * SOFT:
                break
            parts = [f for f in _parts(files, key_of(e["video_url"])) if f["path"] not in gone]
            if parts and not dubs.keep_picture(e):                          # uploaded (public or set to go live): YouTube has the full copy
                drop(parts, "over the storage limit: full copy is on YouTube")
                patches[e["id"]] = {**patches.get(e["id"], {}), "archived": True}

    # 6. still too big (or a deep clean): previews of videos already live (YouTube has them), oldest first
    if deep or left() > LIMIT_MB * SOFT:
        old = sorted([e for e in eps if e["status"] == "published" and key_of(e.get("video_url"))
                      and (_parse(e.get("published_at")) or now) < now - timedelta(hours=GRACE_HOURS)],
                     key=lambda e: e.get("published_at") or "")
        for e in old:
            if not deep and left() <= LIMIT_MB * SOFT:
                break
            if dubs.keep_picture(e):
                continue
            vk = key_of(e["video_url"])
            drop([f for f in files if f["path"] == vk or f["path"].startswith(vk + ".part")], "over the storage limit: video is on YouTube")
            patches[e["id"]] = {**patches.get(e["id"], {}), "video_url": None, "archived": True}

    freed = sum(f["size"] for f in files if f["path"] in gone) / 1e6
    if not dry:
        _delete(sorted(gone))
        for eid, p in patches.items():
            db.update("episodes", eid, p)
        if gone:
            db.log(f"Storage cleanup: removed {len(gone)} files, freed {freed:.0f} MB "
                   f"({before['used_mb'] - freed:.0f} of {LIMIT_MB} MB used)", "info")
    if not dry:
        db.set_setting("storage_usage", {**usage([f for f in files if f["path"] not in gone]),
                                         "at": now.isoformat(timespec="seconds"), "freed_mb": round(freed, 1)})
    reasons: dict[str, int] = {}
    for why in gone.values():
        reasons[why] = reasons.get(why, 0) + 1
    return {"before": before, "freed_mb": round(freed, 1), "after_mb": round(before["used_mb"] - freed, 1),
            "removed": len(gone), "reasons": reasons, "episodes_updated": len(patches), "dry_run": dry}


def maintain(now: datetime | None = None) -> dict:
    """Run by every heartbeat: clean at HIGH or more; deep clean every DEEP_EVERY_DAYS days."""
    db = get_db()
    now = now or datetime.now(timezone.utc)
    last = _parse((db.get_setting("storage_deep_clean") or {}).get("at"))
    if not last or now - last >= timedelta(days=DEEP_EVERY_DAYS):
        res = cleanup(deep=True)
        db.set_setting("storage_deep_clean", {"at": now.isoformat(timespec="seconds"), "freed_mb": res["freed_mb"]})
        return {"ran": "deep clean (every 3 days)", **res}
    u = usage()
    if u["pct"] is not None and u["pct"] >= 100 * HIGH:
        db.log(f"Storage at {u['pct']:.0f}% (85%+): cleaning now", "warn")
        return {"ran": "clean (storage 85%+)", **cleanup()}
    return {"ran": None, "usage": u}


if __name__ == "__main__":       # python -m app.janitor [--apply]
    import json
    import sys
    print(json.dumps(cleanup(dry="--apply" not in sys.argv), indent=2, default=str), flush=True)
    os._exit(0)
