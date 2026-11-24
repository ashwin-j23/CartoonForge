"""The cold open: something happens, the child is asked, the chorus plays, then straight into the problem."""
from app.kids import writer


def _sc(text, kind="line", spk="hoppy"):
    return {"speaker": spk, "text": text, "kind": kind, "emotion": "happy", "action": "idle", "cast": [spk], "card": None}


def _script():
    return {"key_words": ["push"], "segments": [
        {"kind": "hello", "title": "Go", "set": "road", "scenes": [_sc("Oh no! My wagon is stuck!", spk="bo"),
                                                                   _sc("Can you push with me?", "question"),
                                                                   _sc("Let's get it out!")]},
        {"kind": "story", "title": "Mud", "set": "road", "scenes": [_sc("Snuggle in, it's story time.", spk="nana"),
                                                                    _sc("The wheel is deep in the mud!"), _sc("Splash!"),
                                                                    _sc("Help!"), _sc("We are coming!")]},
        {"kind": "song", "title": "Song", "set": "stage", "scenes": [
            _sc("Sing along!", "sing"), _sc("Push, push, push!", "sing", "mimi"), _sc("Never stop!", "sing", "mimi"),
            _sc("A verse of its own,", "sing", "mimi"), _sc("Push, push, push!", "sing", "mimi"),
            _sc("Never stop!", "sing", "mimi")]}]}


def test_chorus_plays_right_after_the_question_and_the_story_starts_on_the_problem():
    s = writer.cold_open(writer.cold_open(_script()))                      # safe to run twice
    assert [x["text"] for x in s["segments"][0]["scenes"]] == [
        "Oh no! My wagon is stuck!", "Can you push with me?", "Push, push, push!", "Never stop!", "Let's get it out!"]
    assert [x["kind"] for x in s["segments"][0]["scenes"]][2:4] == ["sing", "sing"]
    assert s["segments"][1]["scenes"][0]["text"] == "The wheel is deep in the mud!"


def test_an_opening_without_a_question_gets_one():
    s = _script()
    s["segments"][0]["scenes"].pop(1)
    out = [x for x in writer.cold_open(s)["segments"][0]["scenes"] if x["kind"] == "question"]
    assert len(out) == 1 and "push" in out[0]["text"]


def test_template_episode_still_works_with_a_cold_open():
    s = writer.cold_open(writer.template_script("numbers", "Counting", "preschool", 6))
    assert s["segments"][0]["kind"] == "hello" and any(x["kind"] == "question" for x in s["segments"][0]["scenes"])


def test_cold_open_soundtrack_has_the_chorus_and_stays_short(monkeypatch, tmp_path):
    import numpy as np
    from app import tts
    from app.render import audio
    monkeypatch.setattr(tts, "synth", lambda text, *a, **k: (np.full(int(1.2 * audio.SR), .1, np.float32), [], "fake"))
    monkeypatch.setattr(tts, "trim_silence", lambda a: (a, 0.0))
    monkeypatch.setattr(audio, "voice_chain", lambda v: v)
    s = {**writer.cold_open(_script()), "age_band": "preschool", "category": "stories", "topic": "t"}
    snd = audio.build(s, {}, tmp_path / "a.wav", 24, lambda m: None)
    hello = snd["segments"][0]
    assert hello["end"] - hello["start"] < 13
    assert [x["sing"] for x in snd["scenes"] if x["seg"] == 0] == [False, False, True, True, False]
    assert len(snd["song_regions"]) == 1 and snd["song_regions"][0]["start"] > hello["end"]   # Shorts are cut from the real song


def test_editing_a_scheduled_video_keeps_its_schedule(monkeypatch):
    from app.publish import youtube
    sent = {}

    class R:
        status_code, text = 200, ""

        def raise_for_status(self):
            pass

        def json(self):
            return {"items": [{"snippet": {"title": "T", "description": "", "categoryId": "27"},
                               "status": {"privacyStatus": "private", "publishAt": "2026-12-01T15:00:00Z"}}]}
    monkeypatch.setattr(youtube, "_access_token", lambda rt="": "tok")
    monkeypatch.setattr(youtube.httpx, "get", lambda *a, **k: R())
    monkeypatch.setattr(youtube.httpx, "put", lambda *a, json=None, **k: (sent.update(json), R())[1])
    youtube.update_video("v", made_for_kids=False)
    assert sent["status"]["publishAt"] == "2026-12-01T15:00:00Z"
    youtube.update_video("v", privacy="private")                           # an explicit choice cancels it
    assert "publishAt" not in sent["status"]


def test_trends_use_the_channels_age_band():
    from app.kids import categories, planner
    assert planner._band("preschool", categories.get("world")) == "preschool"
    assert planner._band("preschool", categories.get("puzzles")) in categories.get("puzzles")["bands"]
