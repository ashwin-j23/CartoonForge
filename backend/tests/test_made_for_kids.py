"""Long videos must stay 'made for kids' on YouTube (the worker switches back any that lost it); Shorts are the owner's choice."""
from app.publish import youtube


class _R:
    def __init__(self, data):
        self._d, self.status_code = data, 200

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


def test_videos_that_lost_made_for_kids_are_switched_back(monkeypatch):
    statuses = {"a": True, "b": False, "c": None, "s1": False, "s2": False}
    durations = {"a": "PT7M", "b": "PT9M30S", "c": "PT12M", "s1": "PT58S", "s2": "PT10M"}   # s2: a Short the studio knows

    def fake_get(url, params=None, **_):
        if url.endswith("/channels"):
            return _R({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]})
        if url.endswith("/playlistItems"):
            return _R({"items": [{"contentDetails": {"videoId": v}} for v in statuses]})
        ids = params["id"].split(",")
        return _R({"items": [{"id": v, "status": {"selfDeclaredMadeForKids": statuses[v]}, "contentDetails": {"duration": durations[v]}} for v in ids]})

    fixed = []
    monkeypatch.setattr(youtube, "_access_token", lambda rt="": "tok")
    monkeypatch.setattr(youtube.httpx, "get", fake_get)
    monkeypatch.setattr(youtube, "update_video", lambda vid, rt="", made_for_kids=None, **_: fixed.append((vid, made_for_kids)))
    assert youtube.enforce_made_for_kids(skip={"s2"}) == ["b", "c"]          # Shorts untouched
    assert fixed == [("b", True), ("c", True)]


def test_song_shorts_use_the_title_format_that_took_off():
    import inspect
    from app import pipeline
    assert "🎵 Sing Along! #shorts" in inspect.getsource(pipeline.make_short)


def test_shorts_upload_as_not_made_for_kids_long_videos_as_made_for_kids():
    import inspect
    from app import pipeline
    from app.settings import DEFAULTS
    assert DEFAULTS["shorts_made_for_kids"] is False and DEFAULTS["made_for_kids"] is True
    src = inspect.getsource(pipeline.publish)
    assert 'made_for_kids=bool(s.get("shorts_made_for_kids", False)) if ep.get("kind") == "short" else True' in src
