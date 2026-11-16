"""Heartbeat: an outside scheduler pings it; it starts GitHub workflows for due/queued work, rate-limited."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import config, main
from app.db import get_db


def test_heartbeat_dispatches_due_publish_and_queued_work_once(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "WORKER_MODE", "github")
    monkeypatch.setattr(main, "_dispatch_github", lambda wf="": calls.append(wf or "worker.yml") or True)
    db = get_db()
    db.set_setting("heartbeat", {})
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
    db.insert("episodes", {"kind": "episode", "status": "approved", "publish_at": past, "topic": "Due"})
    db.insert("episodes", {"kind": "episode", "status": "planned", "topic": "Queued"})
    c = TestClient(main.app)
    r = c.post("/api/public/heartbeat").json()                 # public: no login
    assert r["publish"] is True and r["worker"] is True and calls == ["publish.yml", "worker.yml"]
    assert c.get("/api/public/heartbeat").json()["skipped"] == "too soon"     # rate-limited
    assert len(calls) == 2
    # forced (cron) run: publishes again, but the worker was started recently so it isn't started twice
    assert main.heartbeat(force=True).get("worker") is None and calls[-1] == "publish.yml"


def test_heartbeat_is_a_no_op_when_inline(monkeypatch):
    monkeypatch.setattr(config, "WORKER_MODE", "inline")
    get_db().set_setting("heartbeat", {})
    assert main.heartbeat()["mode"] == "inline"
