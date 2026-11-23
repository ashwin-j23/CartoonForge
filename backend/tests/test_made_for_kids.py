"""Every video must stay 'made for kids' on YouTube: the worker re-checks the channel and switches back any that lost it."""
from app.publish import youtube


class _R:
    def __init__(self, data):
        self._d, self.status_code = data, 200

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


def test_videos_that_lost_made_for_kids_are_switched_back(monkeypatch):
    statuses = {"a": True, "b": False, "c": None}

    def fake_get(url, params=None, **_):
        if url.endswith("/channels"):
            return _R({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]})
        if url.endswith("/playlistItems"):
            return _R({"items": [{"contentDetails": {"videoId": v}} for v in statuses]})
        ids = params["id"].split(",")
        return _R({"items": [{"id": v, "status": {"selfDeclaredMadeForKids": statuses[v]}} for v in ids]})

    fixed = []
    monkeypatch.setattr(youtube, "_access_token", lambda rt="": "tok")
    monkeypatch.setattr(youtube.httpx, "get", fake_get)
    monkeypatch.setattr(youtube, "update_video", lambda vid, rt="", made_for_kids=None, **_: fixed.append((vid, made_for_kids)))
    assert youtube.enforce_made_for_kids() == ["b", "c"]
    assert fixed == [("b", True), ("c", True)]


def test_song_shorts_use_the_title_format_that_took_off():
    import inspect
    from app import pipeline
    assert "🎵 Sing Along! #shorts" in inspect.getsource(pipeline.make_short)
