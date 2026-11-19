"""On-time publishing: upload ahead as a YouTube-scheduled video; posting zone follows the audience."""
from datetime import datetime, timedelta, timezone

from app import pipeline, storage
from app.db import get_db
from app.kids import growth
from app.publish import youtube


def _approved(at):
    return get_db().insert("episodes", {"kind": "episode", "status": "approved", "topic": "Moon", "category": "space",
                                        "video_url": "x.mp4", "meta": {"title": "Moon", "description": "Hi."},
                                        "publish_at": at.isoformat(timespec="seconds")})


def test_future_slot_is_uploaded_as_youtube_scheduled_and_past_slot_goes_public(monkeypatch, tmp_path):
    calls = []
    f = tmp_path / "v.mp4"
    f.write_bytes(b"0")
    monkeypatch.setattr(storage, "fetch", lambda url: f)
    monkeypatch.setattr(youtube, "upload", lambda *a, **k: calls.append((a[4], k.get("publish_at"))) or {"id": "v1", "url": "u", "privacy": a[4]})
    monkeypatch.setattr(youtube, "ensure_playlist", lambda *a, **k: "p")
    monkeypatch.setattr(youtube, "add_to_playlist", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "make_short", lambda eid: None)
    for e in get_db().query("episodes", eq={"status": "approved"}):
        get_db().update("episodes", e["id"], {"status": "rejected"})
    now = datetime.now(timezone.utc)
    soon, late, past = _approved(now + timedelta(hours=5)), _approved(now + timedelta(hours=100)), _approved(now - timedelta(minutes=3))
    done = pipeline.publish_due()
    assert past["id"] in done and soon["id"] in done and late["id"] not in done      # 100 h away: not yet
    assert ("public", None) in calls                                               # overdue: public now
    priv = [c for c in calls if c[0] == "private"]
    assert len(priv) == 1 and priv[0][1].endswith("Z")                             # YouTube publishes it on time
    ep = get_db().get("episodes", soon["id"])
    assert ep["status"] == "published" and ep["youtube"]["scheduled_for"] and ep["published_at"][:13] == soon["publish_at"][:13]


def test_pick_timezone_follows_a_clear_leader_only():
    assert growth.pick_timezone({"IN": 50, "US": 20}) is None                        # too few views
    assert growth.pick_timezone({"IN": 700, "US": 200, "GB": 100}) == "Asia/Kolkata"
    assert growth.pick_timezone({"US": 300, "IN": 300, "GB": 250, "PH": 250}) is None  # nobody clearly leads


def test_bedtime_episodes_take_the_last_slot_of_the_day():
    from zoneinfo import ZoneInfo
    from app.settings import app_settings
    s = app_settings()
    at = pipeline.slot_for({"category": "bedtime"})
    assert datetime.fromisoformat(at).astimezone(ZoneInfo(s["timezone"])).strftime("%H:%M") == max(s["post_times"])


def test_shorts_never_share_a_time():
    db = get_db()
    at = datetime(2030, 1, 1, 23, 0, tzinfo=timezone.utc)
    db.insert("episodes", {"kind": "short", "status": "approved", "topic": "A", "publish_at": at.isoformat(timespec="seconds")})
    assert pipeline.short_slot(at).startswith("2030-01-02T00:00")          # same minute -> an hour later
    assert pipeline.short_slot(at + timedelta(minutes=2)).startswith("2030-01-02T00:02")   # 2 min apart is too close
