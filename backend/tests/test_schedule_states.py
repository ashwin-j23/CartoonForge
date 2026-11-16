"""Schedule page states: live / uploaded (YouTube-scheduled) / uploading / waiting / late."""
from app.main import _sched_state

NOW = "2026-11-16T15:00:00+00:00"


def test_states():
    assert _sched_state({"status": "published", "published_at": "2026-11-16T13:43:10+00:00", "youtube": {}}, NOW)[0] == "live"
    up = {"status": "published", "published_at": "2026-11-16T21:00:00+00:00", "youtube": {"scheduled_for": "2026-11-16T21:00:00Z"}}
    assert _sched_state(up, NOW) == ("uploaded", "2026-11-16T21:00:00+00:00")
    assert _sched_state({**up, "youtube": {"scheduled_for": "2026-11-16T14:00:00Z"}}, NOW)[0] == "live"   # its time came
    assert _sched_state({"status": "publishing", "publish_at": "2026-11-16T16:00:00+00:00"}, NOW)[0] == "uploading"
    assert _sched_state({"status": "approved", "publish_at": "2026-11-17T13:00:00+00:00"}, NOW)[0] == "waiting"
    assert _sched_state({"status": "approved", "publish_at": "2026-11-16T12:30:00+00:00"}, NOW)[0] == "late"
    assert _sched_state({"status": "approved", "publish_at": "2026-11-17T13:00:00+00:00", "error": "503"}, NOW)[0] == "late"
