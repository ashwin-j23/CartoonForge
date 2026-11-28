"""The dubbed channel: one picture, new voices; English never goes there and dubs never go to the main channel."""
import subprocess
from datetime import datetime, timedelta, timezone

import numpy as np

from app import dubs


def _sc(text, kind="line", spk="hoppy"):
    return {"speaker": spk, "text": text, "kind": kind, "emotion": "happy", "action": "idle", "cast": [spk], "card": None}


def _script():
    return {"age_band": "preschool", "category": "stories", "topic": "t", "title_idea": "t", "key_words": ["push"], "segments": [
        {"kind": "hello", "title": "Go", "set": "road", "scenes": [_sc("Oh no!"), _sc("Can you push?", "question")]},
        {"kind": "story", "title": "Mud", "set": "road", "scenes": [_sc("It is deep."), _sc("Help!")]},
        {"kind": "song", "title": "Song", "set": "stage", "scenes": [_sc("Push, push!", "sing"), _sc("Never stop!", "sing")]}]}


def _fake_voice(monkeypatch, secs):
    from app import tts
    from app.render import audio
    monkeypatch.setattr(tts, "synth", lambda text, *a, **k: (np.full(int(secs["v"] * audio.SR), .1, np.float32), [], "fake"))
    monkeypatch.setattr(tts, "trim_silence", lambda a: (a, 0.0))
    monkeypatch.setattr(audio, "voice_chain", lambda v: v)
    return audio


def test_dub_soundtrack_keeps_the_pictures_timing_even_with_longer_lines(monkeypatch, tmp_path):
    secs = {"v": 1.2}
    audio = _fake_voice(monkeypatch, secs)
    en = audio.build(_script(), {}, tmp_path / "en.wav", 24, lambda m: None)
    times = {"segs": [g["start"] for g in en["segments"]], "lines": [g["lines"] for g in en["segments"]]}
    secs["v"] = 1.6                                                        # Spanish needs more words
    es = audio.build({**_script(), "language": "es"}, {"_dub": times}, tmp_path / "es.wav", 24, lambda m: None)
    assert abs(es["duration"] - en["duration"]) < .01
    assert [s["start"] for s in es["scenes"]] == [s["start"] for s in en["scenes"]]
    assert es["tight"] == []
    secs["v"] = 6.0                                                        # far too long: reported, not hidden
    bad = audio.build({**_script(), "language": "es"}, {"_dub": times}, tmp_path / "x.wav", 24, lambda m: None)
    assert len(bad["tight"]) >= 4 and abs(bad["duration"] - en["duration"]) < .01


def test_old_renders_without_line_times_are_scaled_onto_the_stored_segments(monkeypatch, tmp_path):
    audio = _fake_voice(monkeypatch, {"v": 1.2})
    en = audio.build(_script(), {}, tmp_path / "en.wav", 24, lambda m: None)
    tl = [{k: v for k, v in g.items() if k != "lines"} for g in en["segments"]]
    t = dubs.line_times({"timeline": tl, "script": _script()}, tmp_path, {})
    assert abs(t["lines"][1][0][0] - en["segments"][1]["lines"][0][0]) < .05 and len(t["lines"]) == 3


def test_which_languages_are_still_wanted():
    s = {"editions": ["es", "hi", "en", "xx"]}
    assert dubs.wanted({"editions": {}}, s) == ["es", "hi"]
    assert dubs.wanted({"editions": {"es": {"status": "published"}, "ta": {"status": "planned"}}}, s) == ["hi", "ta"]
    assert dubs.wanted({"editions": {"hi": {"status": "failed", "tries": 3}}}, s) == ["es"]
    assert dubs.wanted({"kind": "short"}, s) == [] and dubs.wanted({"kind": "compilation"}, s) == []


def test_a_dub_goes_live_after_english_in_its_own_slot(monkeypatch):
    monkeypatch.setattr(dubs, "app_settings", lambda: {"timezone": "UTC", "dub_times": ["09:00", "17:00"]})
    live = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=13, minute=0, second=0, microsecond=0)
    a = dubs.next_slot([], live)
    assert a == live.replace(hour=17).isoformat(timespec="seconds")
    b = dubs.next_slot([{"editions": {"es": {"publish_at": a}}}], live)
    assert b == (live + timedelta(days=1)).replace(hour=9).isoformat(timespec="seconds")


def test_upload_uses_the_dubbed_channel_with_the_same_picture(monkeypatch, tmp_path):
    from app import config
    from app.publish import youtube
    from app.render import audio as audiomod
    audio = _fake_voice(monkeypatch, {"v": 1.2})
    monkeypatch.setattr(config, "WORK_DIR", tmp_path)
    en = audio.build(_script(), {}, tmp_path / "en.wav", 24, lambda m: None)
    pic = tmp_path / "pic.mp4"
    subprocess.run([config.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=1280x720:r=24:d={en['duration']:.2f}",
                    "-pix_fmt", "yuv420p", str(pic)], check=True)
    ep = {"id": "e1", "status": "published", "published_at": "2026-11-20T13:00:00+00:00", "script": _script(), "timeline": en["segments"],
          "meta": {"title": "T", "tags": ["a"], "localizations": {"es": {"title": "Hola", "description": "Desc"}}}, "editions": {}}

    class DB:
        def get(self, t, i):
            return ep

        def update(self, t, i, p):
            ep.update(p)

        def query(self, *a, **k):
            return [ep]

        def get_setting(self, k, d=None):
            return {"title": "Hoppy World", "t": 9e12}
    monkeypatch.setattr(dubs, "get_db", lambda: DB())
    monkeypatch.setattr(dubs, "token", lambda: "DUB")
    monkeypatch.setattr(dubs, "app_settings", lambda: {"timezone": "UTC", "editions": ["es"]})
    monkeypatch.setattr(dubs.metamod, "translate_script", lambda s, lg, secs=None: {**s, "language": lg})
    monkeypatch.setattr(dubs, "thumb", lambda ep, lg, out: out)
    sent = {}

    def upload(path, title, desc, tags, privacy, th, lang, loc, rt, cat, **kw):
        sent.update(title=title, privacy=privacy, lang=lang, rt=rt, h=dubs._height(path), **kw)
        return {"id": "V1", "url": "https://youtu.be/V1"}
    monkeypatch.setattr(youtube, "upload", upload)
    monkeypatch.setattr(youtube, "ensure_playlist", lambda *a: "P")
    monkeypatch.setattr(youtube, "add_to_playlist", lambda *a: None)
    ed = dubs.make("e1", "es", picture=pic)
    assert ed["status"] == "published", ed
    assert (sent["rt"], sent["lang"], sent["title"], sent["privacy"], sent["made_for_kids"], sent["h"]) == ("DUB", "es", "Hola", "private", True, 720)
    assert sent["publish_at"].endswith("Z") and dubs.wanted(ep) == [] and pic.exists()
    assert audiomod.DUB_MAX_TEMPO < 1.5


def test_dub_description_has_the_chapters_in_its_own_language(monkeypatch):
    monkeypatch.setattr(dubs, "app_settings", lambda: {"channel_name": "Hoppy"})
    monkeypatch.setattr(dubs, "channel_name", lambda: "Hoppy World")
    tl = [{"title": t, "kind": "story", "start": s, "end": s + 60} for t, s in (("Go", 0.3), ("Mud", 60), ("Song", 120))]
    ep = {"timeline": tl, "meta": {"localizations": {"es": {"title": "Hola", "description":
          "Uno. Subscribe to Hoppy!\n\n0:00 Go\n1:00 Mud\n2:00 Song\n\nDos youtube.com/@X?sub_confirmation=1"}}}}
    script = {"segments": [{"title": t} for t in ("Vamos", "Barro", "Canción")]}
    d = dubs.dub_meta(ep, "es", script)["description"]
    assert "1:00 Barro" in d and "2:00 Canción" in d and "Mud" not in d and "youtube.com" not in d and d.startswith("Uno. Subscribe to Hoppy World!") and "Dos" in d
    assert dubs.dub_meta(ep, "es", script)["playlist"].endswith("· Hoppy World")


def test_the_main_channel_refuses_other_languages():
    import inspect
    from app import pipeline
    src = inspect.getsource(pipeline.publish)
    assert "The main channel is English only" in src and "edition_channels" not in src


def test_story_animals_are_never_silently_drawn_as_bears():
    from app.render import designer
    key = lambda s: designer.normalize({"species": s, "kind": "animal", "outfit": "feathers"})   # noqa: E731
    assert [key(s)["_key"] for s in ("eagle", "spider", "ox", "red fox", "elephant", "lamb", "jackdaw")] == \
        ["eagle", "spider", "cow", "fox", "elephant", "sheep", "crow"]
    assert key("eagle")["outfit"] == "none"
