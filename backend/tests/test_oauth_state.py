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
    monkeypatch.setattr(youtube, "exchange_code", lambda code, uri, save=True: got.update(code=code) or "tok")
    monkeypatch.setattr(youtube, "channel_info", lambda rt="": {"id": "UC1"} if rt == "tok" else {"id": "UC2"})
    from app import settings
    saved = {}
    monkeypatch.setattr(settings, "save_secrets", saved.update)
    monkeypatch.setattr(settings, "secret", lambda k: "")
    st = main._oauth_state()                                    # made by "instance A"
    c = TestClient(main.app)                                    # callback served by "instance B"
    r = c.get("/api/youtube/callback", params={"code": "abc", "state": st}, follow_redirects=False)
    assert r.status_code in (302, 307) and "yt=ok" in r.headers["location"] and got["code"] == "abc"
    bad = c.get("/api/youtube/callback", params={"code": "abc", "state": "1.x.y"}, follow_redirects=False)
    assert "yt=error" in bad.headers["location"]


def test_dubbed_channel_is_saved_apart_and_never_the_english_one(monkeypatch):
    from fastapi.testclient import TestClient
    from app import settings
    from app.publish import youtube
    saved, ids = {}, {"new": "UC2", "main": "UC1"}
    monkeypatch.setattr(youtube, "exchange_code", lambda code, uri, save=True: "new")
    monkeypatch.setattr(youtube, "channel_info", lambda rt="": {"id": ids[rt]})
    monkeypatch.setattr(settings, "save_secrets", saved.update)
    monkeypatch.setattr(settings, "secret", lambda k: {"YT_REFRESH_TOKEN": "main"}.get(k, ""))
    c = TestClient(main.app)
    go = lambda: c.get("/api/youtube/callback", params={"code": "a", "state": main._oauth_state("dub")},   # noqa: E731
                       follow_redirects=False).headers["location"]
    assert "yt=dub" in go() and saved == {"YT_DUB_REFRESH_TOKEN": "new"}
    saved.clear()
    ids["new"] = "UC1"                                          # the owner picked Hoppy Hop Hop by mistake
    assert "yt=error" in go() and saved == {}
