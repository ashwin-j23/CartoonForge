"""YouTube OAuth state is signed, not kept in memory: a callback on another serverless instance still works."""
import time

from app import main


def test_signed_state_round_trip_and_rejections(monkeypatch):
    st = main._oauth_state()
    assert main._state_ok(st)                                   # verifiable with no shared memory
    ts, nonce, sig = st.split(".")
    assert not main._state_ok(f"{ts}.{nonce}x.{sig}")           # tampered
    assert not main._state_ok("garbage") and not main._state_ok("")
    real = time.time
    monkeypatch.setattr(main.time, "time", lambda: real() + 1000)
    assert not main._state_ok(st)                               # older than 15 minutes


def test_callback_accepts_state_from_another_instance(monkeypatch):
    from fastapi.testclient import TestClient
    from app.publish import youtube
    got = {}
    monkeypatch.setattr(youtube, "exchange_code", lambda code, uri: got.update(code=code) or "tok")
    st = main._oauth_state()                                    # made by "instance A"
    c = TestClient(main.app)                                    # callback served by "instance B"
    r = c.get("/api/youtube/callback", params={"code": "abc", "state": st}, follow_redirects=False)
    assert r.status_code in (302, 307) and "yt=ok" in r.headers["location"] and got["code"] == "abc"
    bad = c.get("/api/youtube/callback", params={"code": "abc", "state": "1.x.y"}, follow_redirects=False)
    assert "yt=error" in bad.headers["location"]
