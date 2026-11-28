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


def test_daily_upload_limit_pauses_the_channel_without_using_up_tries(monkeypatch, tmp_path):
    from app import config
    store = {"e": {"id": "e", "editions": {"es": {"status": "planned", "tries": 0}}}, "settings": {}}

    class DB:
        def get(self, t, i):
            return store["e"]

        def update(self, t, i, p):
            store["e"].update(p)

        def get_setting(self, k, d=None):
            return store["settings"].get(k, d)

        def set_setting(self, k, v):
            store["settings"][k] = v
    monkeypatch.setattr(dubs, "get_db", lambda: DB())
    monkeypatch.setattr(dubs, "token", lambda: "DUB")
    monkeypatch.setattr(config, "WORK_DIR", tmp_path)

    def boom(*a, **k):
        raise RuntimeError('YouTube init failed 400: {"message": "The user has exceeded the number of videos they may upload."}')
    monkeypatch.setattr(dubs, "_height", boom)
    ed = dubs.make("e", "es", picture=tmp_path / "p.mp4")
    assert ed["status"] == "planned" and ed["tries"] == 0 and "upload limit" in ed["error"]
    assert dubs.paused()
    monkeypatch.setattr(dubs, "due", lambda: [("e", "es")])
    monkeypatch.setattr(dubs, "app_settings", lambda: {})
    assert dubs.run() == []                    # nothing is dubbed (and nothing wasted) until the limit resets


def test_dub_short_is_cut_stored_and_uploaded_after_its_dub(monkeypatch, tmp_path):
    from app import config, storage
    from app.publish import youtube
    from app.render import episode as epr
    ep = {"id": "e", "status": "published", "song_regions": [{"start": 100, "end": 180}], "timeline": [],
          "meta": {"tags": ["a"], "localizations": {"es": {"title": "Hola Hoppy | para niños"}}},
          "editions": {"es": {"status": "published", "publish_at": "2026-12-01T14:00:00+00:00",
                              "youtube": {"url": "https://youtu.be/D"}}}}
    store = {"settings": {}}

    class DB:
        def get(self, t, i):
            return ep

        def update(self, t, i, p):
            ep.update(p)

        def query(self, *a, **k):
            return [ep]

        def get_setting(self, k, d=None):
            return store["settings"].get(k, d) if k != "dub_channel_cache" else {"title": "Hoppy World", "t": 9e12}

        def set_setting(self, k, v):
            store["settings"][k] = v
    monkeypatch.setattr(dubs, "get_db", lambda: DB())
    monkeypatch.setattr(dubs, "token", lambda: "DUB")
    monkeypatch.setattr(dubs, "app_settings", lambda: {"timezone": "UTC", "shorts_made_for_kids": False})
    monkeypatch.setattr(config, "WORK_DIR", tmp_path)
    cuts = {}
    monkeypatch.setattr(epr, "cut_short", lambda v, s, e, out, cap, crop_bottom=0: cuts.update(s=s, e=e, cap=cap) or out)
    monkeypatch.setattr(storage, "put", lambda f, k, t: "https://x/storage/v1/object/public/b/" + k)
    monkeypatch.setattr(storage, "fetch", lambda u: tmp_path / "s.mp4")
    monkeypatch.setattr(storage, "remove", lambda ks: None)
    script = {"language": "es", "segments": [{"kind": "song", "scenes": [
        {"kind": "sing", "text": "¡Gracias, gracias!"}, {"kind": "sing", "text": "Sí, es verdad"},
        {"kind": "sing", "text": "¡Gracias, gracias!"}, {"kind": "sing", "text": "Sí, es verdad"}]}]}
    dubs.make_short(ep, "es", tmp_path / "dub.mp4", script, tmp_path)
    sh = ep["editions"]["es"]["short"]
    assert cuts == {"s": 100, "e": 140, "cap": "¡Gracias, gracias!"} and sh["status"] == "planned"
    assert sh["title"] == "Hola Hoppy 🎵 ¡Canta con nosotros!"
    assert dubs.short_name("¡Hoppy ayuda al carretero! Vídeos educativos 🚜 Esfuérzate") == "¡Hoppy ayuda al carretero!"
    assert dubs.short_name("हॉपी ने की मदद! बच्चों के लिए शैक्षिक वीडियो 🚜 अपनी पूरी") == "हॉपी ने की मदद!"
    assert dubs.short_name("Petualangan Rumah Tikus - Cerita Pengantar Tidur") == "Petualangan Rumah Tikus"
    sent = {}
    monkeypatch.setattr(youtube, "upload", lambda f, title, desc, tags, privacy, th, lang, loc, rt, cat, **kw:
                        sent.update(title=title, desc=desc, rt=rt, lang=lang, **kw) or {"id": "S", "url": "https://youtube.com/shorts/S"})
    assert dubs.upload_shorts() == ["e:es:short"]
    assert sent["rt"] == "DUB" and sent["short"] and sent["made_for_kids"] is False and "#cancionesinfantiles" in sent["desc"]
    assert sent["publish_at"] > "2026-12-02T02:00" and ep["editions"]["es"]["short"]["status"] == "published"
    script["language"] = "hi"
    assert dubs.short_cut(ep, script)[2] == ""                 # no caption the font can't draw
