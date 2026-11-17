"""Storage cleanup keeps what's needed and frees the rest."""
import os
import time
from datetime import datetime, timedelta, timezone

from app import config, janitor, pipeline
from app.db import get_db


def _file(key, mb=1, age_h=24):
    p = config.MEDIA_DIR / key
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * int(mb * 1_000_000))
    t = time.time() - age_h * 3600
    os.utime(p, (t, t))
    return f"/media/{key}"


def _iso(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def test_cleanup_rules(monkeypatch):
    db = get_db()
    for e in db.query("episodes", limit=1000):
        db.delete("episodes", e["id"])
    import shutil
    shutil.rmtree(config.MEDIA_DIR, ignore_errors=True)
    # waiting episode with an old render left behind by a re-render
    w = db.insert("episodes", {"kind": "episode", "status": "approved", "topic": "W"})
    keep_v = _file(f"{w['id']}/episode-2.mp4")
    _file(f"{w['id']}/episode-2.mp4.part000", 5)
    db.update("episodes", w["id"], {"video_url": keep_v, "thumb_url": _file(f"{w['id']}/thumb-2.jpg")})
    _file(f"{w['id']}/episode-1.mp4"); _file(f"{w['id']}/episode-1.mp4.part000", 5)     # superseded
    _file(f"{w['id']}/episode-3.mp4.part000", 5, age_h=1)                               # render in flight: keep
    # published 5 days ago: parts go, preview stays
    p = db.insert("episodes", {"kind": "episode", "status": "published", "topic": "P", "published_at": _iso(5)})
    pv = _file(f"{p['id']}/episode-1.mp4")
    _file(f"{p['id']}/episode-1.mp4.part000", 5)
    db.update("episodes", p["id"], {"video_url": pv})
    # published yesterday: untouched
    y = db.insert("episodes", {"kind": "episode", "status": "published", "topic": "Y", "published_at": _iso(1)})
    db.update("episodes", y["id"], {"video_url": _file(f"{y['id']}/episode-1.mp4")})
    _file(f"{y['id']}/episode-1.mp4.part000", 5)
    # rejected long ago: everything goes
    r = db.insert("episodes", {"kind": "episode", "status": "rejected", "topic": "R"})
    db.update("episodes", r["id"], {"video_url": _file(f"{r['id']}/episode-1.mp4"), "thumb_url": _file(f"{r['id']}/t.jpg")})
    monkeypatch.setattr(janitor, "_parse", lambda iso, _real=janitor._parse: (
        datetime.now(timezone.utc) - timedelta(days=30)) if iso == db.get("episodes", r["id"]).get("updated_at") else _real(iso))
    _file("characters/hoppy.png")                                                         # not ours to manage

    plan = janitor.cleanup(dry=True)
    assert plan["dry_run"] and (config.MEDIA_DIR / f"{w['id']}/episode-1.mp4").exists()
    res = janitor.cleanup()
    left = {str(f.relative_to(config.MEDIA_DIR)) for f in config.MEDIA_DIR.rglob("*") if f.is_file()}
    assert f"{w['id']}/episode-2.mp4" in left and f"{w['id']}/episode-2.mp4.part000" in left
    assert f"{w['id']}/episode-1.mp4" not in left and f"{w['id']}/episode-1.mp4.part000" not in left
    assert f"{w['id']}/episode-3.mp4.part000" in left
    assert f"{p['id']}/episode-1.mp4" in left and f"{p['id']}/episode-1.mp4.part000" not in left
    assert db.get("episodes", p["id"]).get("archived") is True
    assert f"{y['id']}/episode-1.mp4.part000" in left
    assert not any(x.startswith(r["id"]) for x in left) and db.get("episodes", r["id"]).get("video_url") is None
    assert "characters/hoppy.png" in left
    assert res["removed"] == 5 and res["freed_mb"] > 12


def test_uploaded_videos_keep_their_slot():
    db = get_db()
    slot = pipeline.free_slots(1)[0]
    db.insert("episodes", {"kind": "episode", "status": "published", "topic": "S", "published_at": slot})
    assert slot not in pipeline.free_slots(3)
