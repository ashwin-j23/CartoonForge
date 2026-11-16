"""On Vercel nothing heavy runs in-process: no voices there, and functions stop after 5 minutes."""
from fastapi.testclient import TestClient

from app import config, main, pipeline


def _client():
    c = TestClient(main.app)
    tok = c.post("/api/login", json={"password": config.ADMIN_PASSWORD}).json()["token"]
    return c, {"Authorization": "Bearer " + tok}


def test_vercel_never_runs_heavy_work_inline(monkeypatch):
    monkeypatch.setattr(config, "ON_VERCEL", True)
    monkeypatch.setattr(config, "WORKER_MODE", "github")
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")                 # render farm can't be started
    while not main._jobs.empty():
        main._jobs.get_nowait()
    assert main.run(pipeline.process, "x") is False and main._jobs.empty()
    c, h = _client()
    r = c.post("/api/tick", headers=h)
    assert r.status_code == 503 and "GITHUB_TOKEN" in r.json()["detail"]
    assert c.post("/api/automation/run", headers=h).status_code == 503
    assert main._jobs.empty()


def test_vercel_dispatches_when_it_can(monkeypatch):
    monkeypatch.setattr(config, "ON_VERCEL", True)
    monkeypatch.setattr(config, "WORKER_MODE", "github")
    monkeypatch.setattr(main, "_dispatch_github", lambda: True)
    assert main.run(pipeline.publish, "x") is True and main._jobs.empty()
