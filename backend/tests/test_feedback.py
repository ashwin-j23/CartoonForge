"""Parent feedback: public form endpoints, privacy scrubbing, rate limit, summary, description link."""
import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.db import get_db
from app.kids import feedback
from app.settings import save_app_settings


def _published():
    return get_db().insert("episodes", {"kind": "episode", "status": "published", "topic": "Moon", "category": "space",
                                        "meta": {"title": "Goodnight Moon"}, "youtube": {"url": "https://youtu.be/x"}})


def test_clean_scrubs_personal_details_and_validates():
    row = feedback.clean({"enjoyed": "loved", "style": "5", "animation": 9, "change": "mail me at a.b@c.com or +91 98765 43210",
                          "request": "more dinosaurs https://spam.example", "age_band": "preschool", "role": "boss"})
    assert row["style"] == 5 and row["animation"] is None and row["role"] is None
    assert "@" not in row["change"] and "98765" not in row["change"] and "spam" not in row["request"]
    with pytest.raises(ValueError):
        feedback.clean({"role": "parent"})                          # nothing answered


def test_public_endpoints_rate_limit_and_honeypot():
    main._fb_hits.clear()
    ep = _published()
    c = TestClient(main.app)
    info = c.get(f"/api/public/episode/{ep['id']}").json()
    assert info["title"] == "Goodnight Moon" and "script" not in info
    draft = get_db().insert("episodes", {"kind": "episode", "status": "review", "topic": "Secret"})
    assert c.get(f"/api/public/episode/{draft['id']}").status_code == 404     # unpublished stays private
    before = len(feedback.rows())
    assert c.post("/api/public/feedback", json={"website": "bot", "enjoyed": "loved"}).json() == {"ok": True}
    assert len(feedback.rows()) == before                            # honeypot: silently dropped
    for _ in range(5):
        assert c.post("/api/public/feedback", json={"episode_id": ep["id"], "enjoyed": "loved", "style": 5,
                                                    "request": "Dinosaurs"}).status_code == 200
    assert c.post("/api/public/feedback", json={"enjoyed": "ok"}).status_code == 429
    h = {"Authorization": "Bearer " + c.post("/api/login", json={"password": config.ADMIN_PASSWORD}).json()["token"]}
    data = c.get("/api/feedback", headers=h).json()
    assert data["summary"]["count"] >= 5 and data["summary"]["avg"]["style"] == 5
    assert data["summary"]["requests"][0]["topic"] == "dinosaurs"
    assert any(i.get("episode_title") == "Goodnight Moon" for i in data["items"])
    assert c.get("/api/feedback").status_code == 401                 # owner-only


def test_falls_back_to_the_activity_log_without_the_table(monkeypatch):
    db = get_db()
    real = db.insert
    monkeypatch.setattr(db, "insert", lambda t, r: (_ for _ in ()).throw(RuntimeError("no table")) if t == "feedback" else real(t, r))
    feedback.save({"enjoyed": "ok", "request": "trains", "episode_id": None})
    monkeypatch.setattr(db, "insert", real)
    assert any(r.get("request") == "trains" for r in feedback.rows())


def test_description_gets_the_feedback_link_once():
    save_app_settings({"site_url": "https://cartoonforge.vercel.app"})
    d = feedback.with_link("Hook line.\n\nMore text.", "abc123")
    assert d.startswith("Hook line.\n\n👨‍👩‍👧 Grown-ups") and "https://cartoonforge.vercel.app/#/feedback?v=abc123" in d
    assert feedback.with_link(d, "abc123") == d
    save_app_settings({"site_url": ""})


def test_never_links_to_localhost_and_replaces_an_old_line(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "http://localhost:8000")
    save_app_settings({"site_url": "https://cartoonforge.vercel.app"})
    assert feedback.site_url() == "https://cartoonforge.vercel.app"
    old = "Hook.\n\n👨‍👩‍👧 Grown-ups: how was this episode? Tell us 👉 http://localhost:8000/#/feedback?v=e1\n\nMore."
    new = feedback.with_link(old, "e1")
    assert "localhost" not in new and new.count("Grown-ups: how was this episode?") == 1
    save_app_settings({"site_url": ""})
    assert feedback.site_url() == "" and feedback.with_link("x", "e1") == "x"      # no public address: no link
