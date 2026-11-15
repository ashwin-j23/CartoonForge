"""Full auto mode: strict publishing gates, auto-approve, auto-retry, no demo churn, API."""
from datetime import datetime, timedelta, timezone

from app import automation, pipeline
from app.db import get_db
from app.settings import save_app_settings


def _good_ep(**kw):
    ep = {"kind": "episode", "status": "review", "topic": "Bees", "category": "science", "age_band": "preschool",
          "script": {"writer": "ai", "segments": []}, "safety": {"ok": True}, "qa": {"ok": True, "checks": []},
          "critic": {"score": 9.0}, "video_url": "/media/x/episode.mp4", "minutes": 12}
    ep.update(kw)
    return get_db().insert("episodes", ep)


def test_gates_block_demo_unsafe_low_score_and_no_youtube(monkeypatch):
    save_app_settings({"kill_switch": False, "quality_bar": 7.5})
    monkeypatch.setattr(automation, "_yt", lambda: True)
    assert automation.gates(_good_ep()) == []
    assert any("demo" in w for w in automation.gates(_good_ep(script={"writer": "template"})))
    assert any("safety" in w for w in automation.gates(_good_ep(safety={"ok": False})))
    assert any("psychology" in w for w in automation.gates(_good_ep(critic={"score": 6})))
    monkeypatch.setattr(automation, "_yt", lambda: False)
    assert any("YouTube" in w for w in automation.gates(_good_ep()))


def test_auto_approve_only_passing_episodes(monkeypatch):
    monkeypatch.setattr(automation, "_yt", lambda: True)
    save_app_settings({"full_auto": True, "kill_switch": False})
    good, demo = _good_ep(), _good_ep(script={"writer": "template"})
    done = automation.auto_approve()
    db = get_db()
    assert good["id"] in done and db.get("episodes", good["id"])["status"] == "approved"
    d = db.get("episodes", demo["id"])
    assert d["status"] == "review" and any("demo" in w for w in d["auto_hold"])
    save_app_settings({"full_auto": False})


def test_auto_retry_waits_and_caps():
    db = get_db()
    save_app_settings({"auto_retry": True, "max_retries": 2})
    ep = _good_ep(status="failed", error="Render failed: boom", retries=0)
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    db.update("episodes", ep["id"], {"updated_at": old})
    # LocalDB.update stamps updated_at; force the old value back into the stored document
    row = db.get("episodes", ep["id"])
    row["updated_at"] = old
    import json
    db.conn.execute("UPDATE episodes SET doc=? WHERE id=?", (json.dumps(row), ep["id"]))
    db.conn.commit()
    assert ep["id"] in automation.auto_retry()
    r = db.get("episodes", ep["id"])
    assert r["status"] == "scripted" and r["retries"] == 1
    blocked = _good_ep(status="failed", error="Safety gate blocked: x", retries=0)
    assert blocked["id"] not in automation.auto_retry()


def test_no_demo_churn_without_ai(monkeypatch):
    monkeypatch.setattr(pipeline, "has_ai", lambda: False)
    db = get_db()
    for e in db.query("episodes", limit=500):
        db.delete("episodes", e["id"])
    save_app_settings({"auto_generate": True, "episodes_per_day": 3})
    pipeline._keep_full()
    pipeline._keep_full()
    planned = [e for e in db.query("episodes", limit=50) if e["status"] == "planned"]
    assert len(planned) == 1


def test_api_status_and_toggle():
    from fastapi.testclient import TestClient
    from app import config, main
    c = TestClient(main.app)
    h = {"Authorization": "Bearer " + c.post("/api/login", json={"password": config.ADMIN_PASSWORD}).json()["token"]}
    st = c.get("/api/automation", headers=h).json()
    assert {"enabled", "ready", "checklist", "next_slots", "held", "actions"} <= set(st)
    on = c.put("/api/automation", headers=h, json={"enabled": True}).json()
    assert on["enabled"] is True and c.get("/api/settings", headers=h).json()["autopilot"] is True
    off = c.put("/api/automation", headers=h, json={"enabled": False}).json()
    assert off["enabled"] is False
