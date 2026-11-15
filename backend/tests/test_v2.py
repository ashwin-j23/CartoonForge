"""Step 16: character library, art style per episode, AI animation compositing (with a fake provider)."""
import subprocess
from pathlib import Path

from app import config
from app.kids import library, writer


def _script_with_guest():
    s = writer.template_script("numbers", "Counting with Pip", "preschool", 6, seed=1)
    s["characters"] = [{"id": "tortoise", "name": "Tortoise", "kind": "animal", "species": "tortoise",
                        "gender": "m", "age": "old"}]
    s["segments"][1]["scenes"][0]["speaker"] = "tortoise"
    return s


def test_harvest_saves_cameo_and_promotes_after_three_episodes():
    s = _script_with_guest()
    for i in range(3):
        library.harvest(s, f"ep{i}")
    row = library.get("tortoise")
    assert row["appearances"] == 3 and row["tier"] == "recurring"
    assert "tortoise" in library.bible()


def test_library_design_is_reused_by_name():
    library.create({"name": "Wolf", "species": "wolf", "colors": {"main": "#334455"}, "voice": "kokoro:am_onyx"},
                   tier="cameo")
    hit = library.match({"name": "The Big Bad Wolf", "species": "wolf"})
    assert hit and hit["id"] == "wolf"
    chars = writer._from_library([{"id": "big_wolf", "name": "Big Bad Wolf", "species": "wolf"}])
    assert chars[0]["id"] == "wolf" and chars[0]["colors"]["main"] == "#334455"
    from app.kids import cast
    assert cast.guest_profile(chars[0])[0] == "kokoro:am_onyx"


def test_attach_adds_library_design_for_used_ids():
    library.create({"id": "owlbert", "name": "Owlbert", "species": "owl"}, tier="recurring")
    s = writer.template_script("numbers", "Counting with Pip", "preschool", 6, seed=1)
    s["segments"][0]["scenes"][0]["cast"] = ["pip", "owlbert"]
    library.attach(s)
    assert any(g["id"] == "owlbert" and g["species"] == "owl" for g in s["characters"])


def test_keyword_story_designer_without_ai():
    res = library.design_from_story("The Ant and the Grasshopper", "An ant worked all summer. A grasshopper sang.")
    ids = {c["id"] for c in res["characters"]}
    assert {"ant", "grasshopper"} <= ids


def test_style_for_prefers_episode_choice():
    from app.pipeline import style_for
    assert style_for({"art_style": "paper", "variant": {"style": "pixel"}}, {"art_style": "auto"}) == "paper"
    assert style_for({"art_style": "auto", "variant": {"style": "pixel"}}, {"art_style": "auto"}) == "pixel"
    assert style_for({}, {"art_style": "auto"}) == "classic"


def _color_video(path: Path, color: str, secs: float, size="320x180"):
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}:r=24:d={secs}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(path)], check=True)


def test_hero_mode_composites_clips_and_keeps_soundtrack(tmp_path: Path, monkeypatch):
    from app.render import aivideo
    from app.render.episode import probe_duration
    base = tmp_path / "base.mp4"
    _color_video(base, "blue", 30)
    monkeypatch.setattr(aivideo, "configured", lambda: ["runway"])
    calls = []

    def fake(img, prompt, secs, out):
        assert img[:2] == b"\xff\xd8" and "EXACTLY" in prompt
        calls.append(secs)
        _color_video(out, "red", secs, "1280x720")
    monkeypatch.setitem(aivideo.CALL, "runway", fake)
    script = writer.template_script("numbers", "Counting with Pip", "preschool", 6, seed=1)
    scenes = [{"seg": 0, "idx": 0, "speaker": "sunny", "start": 2.0, "end": 5.0, "kind": "line"},
              {"seg": 2, "idx": 0, "speaker": "mimi", "start": 18.0, "end": 22.0, "kind": "sing"}]
    script["segments"][2]["kind"] = "song"
    out = {"video": base, "scenes": scenes, "W": 320, "H": 180, "fps": 24, "duration": 30.0}
    rep = aivideo.enhance(script, out, {"_animation": "hero", "ai_video_budget_usd": 1, "ai_video_hero_shots": 4,
                                        "_style": "paper"}, tmp_path)
    assert rep["provider"] == "runway" and len(calls) == 2 and all(c in (5, 10) for c in calls)
    assert [c["status"] for c in rep["clips"]] == ["ok", "ok"] and rep["usd"] == 1.0
    assert out["video"].name == "episode_ai.mp4" and abs(probe_duration(out["video"]) - 30) < .5
    # t=3 s and t=20 s are red AI clips, t=15 s is still the blue code render
    def px(t):
        raw = subprocess.run([config.FFMPEG, "-v", "error", "-ss", str(t), "-i", str(out["video"]), "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1x1", "-"], capture_output=True).stdout
        return tuple(raw[:3])
    assert px(3)[0] > 150 and px(15)[2] > 150 and px(20)[0] > 150
    a = subprocess.run([config.FFMPEG, "-i", str(out["video"])], capture_output=True, text=True).stderr
    assert "Audio: aac" in a


def test_budget_cap_skips_extra_clips():
    from app.render import aivideo
    est = aivideo.estimate("full", 12, "runway")
    assert est["usd"] > 20 and est["clips"] > 100
    assert aivideo.clip_len("runway", 3) == 5 and aivideo.clip_len("runway", 9) == 10
    assert aivideo.clip_len("omni", 1) == 3 and aivideo.clip_len("kling", 40) == 30


def test_expressions_change_on_cue_words_and_listeners_react():
    from app.render import expression as ex
    words = [{"w": w, "s": 10 + i * .4, "e": 10.3 + i * .4} for i, w in
             enumerate("We walked and walked and then oh no the bridge broke".split())]
    sc = {"start": 10.0, "voice_end": 14.4, "end": 15.0, "kind": "line", "words": words}
    track = ex.speaker_track(sc, {"emotion": "happy"})
    emos = [e for _, e in track]
    assert emos[0] == "happy" and "worried" in emos
    t_worry = next(s for s, e in track if e == "worried")
    assert ex.at(track, t_worry + .1)[0] == "worried"
    # a listener mirrors a beat later, not instantly
    assert ex.listener(track, sc, t_worry + .05, 0, False)[0] != "worried"
    assert ex.listener(track, sc, t_worry + .8, 0, False)[0] == "worried"
    # changes never flicker
    times = [s for s, _ in track]
    assert all(b - a >= ex.MIN_GAP - 1e-6 for a, b in zip(times, times[1:]))


def test_question_pause_anticipation_and_bedtime_stays_gentle():
    from app.render import expression as ex
    words = [{"w": w, "s": i * .4, "e": i * .4 + .3} for i, w in enumerate("How many apples can you count?".split())]
    sc = {"start": 0.0, "voice_end": 2.4, "end": 6.0, "kind": "question", "words": words}
    track = ex.speaker_track(sc, {"emotion": "happy"})
    assert ex.at(track, 3.0)[0] == "happy" and ex.at(track, 5.8)[0] == "excited"
    assert ex.listener(track, sc, 3.5, 2, True)[0] == "thinking"
    calm = [{"w": w, "s": i * .4, "e": i * .4 + .3} for i, w in enumerate("Wow yay goodnight little sprouts".split())]
    t2 = ex.speaker_track({"start": 0, "voice_end": 2, "end": 2.5, "kind": "line", "words": calm}, {"emotion": "sleepy"})
    assert all(e in ex.GENTLE for _, e in t2)


def test_removed_looks_are_gone_and_fall_back():
    from app.pipeline import style_for
    from app.render.styles import STYLES
    assert not {"claymation", "bricks", "diorama", "lowpoly"} & set(STYLES)
    assert style_for({"art_style": "claymation"}, {"art_style": "bricks"}) == "classic"


def test_palettes_from_research_choice_and_readability():
    from app.render import palette as P
    assert len([p for p in P.PALETTES.values() if p["source"] == P.FILMORA]) == 15
    assert P.PALETTES["alphabet_classroom"]["colors"] == ["#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93"]
    assert P.choose("numbers", "preschool") == "alphabet_classroom"
    assert P.choose("numbers", "toddler") == "dreamy_nursery"             # soft pastels for the youngest
    assert P.choose("space", "preschool") == "cotton_candy"               # dark neon only for older kids
    assert P.choose("vehicles", "big") == "superhero_pop"
    assert P.choose("numbers", "preschool", "music_room") == "music_room"
    assert P.vivid_cap("toddler") == 1.0 < P.vivid_cap("preschool") < P.vivid_cap("big")
    for pid in P.PALETTES:                                                 # white text always readable on buttons
        P.set_current(pid)
        assert P.contrast(P.button(), (255, 255, 255)) >= 3, pid
    P.set_current("alphabet_classroom")
    assert P.highlight() == (255, 202, 58)                                 # sing-along word = the palette's sunny yellow
