"""Regression tests: camera never slices characters/cards, short iris, friendly faces, Sunny clear of cards,
honest QA length, full-length demo script, no onnxruntime telemetry."""
import bisect
import os

import numpy as np
import pytest

from app.kids import cast as castmod
from app.kids import psychology, writer
from app.render import characters, episode
from app.render import frame as fr


def _timeline(pace: str, minutes: float = 12, band: str = "preschool"):
    s = writer.template_script("numbers", "Counting with Pip and Friends", band, minutes, seed=5)
    settings = {"pace": pace, "art_style": "classic", "render_scale": .2, "quality": "normal"}
    snd = episode.estimate_audio(s, 24)
    W, H = episode._size(settings)
    return fr.Timeline(s, snd, W, H, 24, settings)


def _scene_layout(tl, sc):
    data = tl.scene_data(sc)
    card = data.get("card")
    on = [c for c in data.get("cast", []) if (c in castmod.CAST or c in tl.guests) and c != "sunny"][:3] or [castmod.STAR]
    xs = ({1: [.2], 2: [.13, .31], 3: [.09, .22, .35]} if card else {1: [.5], 2: [.36, .64], 3: [.27, .5, .73]})[len(on)]
    return data, card, on, xs


@pytest.mark.parametrize("pace", ["calm", "lively", "rapid"])
def test_camera_never_slices_a_character_or_card(pace):
    tl = _timeline(pace)
    names = set()
    for si, sc in enumerate(tl.scenes):
        data, card, on, xs = _scene_layout(tl, sc)
        side = fr._sunny_side(tl, sc["seg"])
        shots = fr._shots(tl, si, sc, data, on, xs, card, data["speaker"], tl.W, tl.H, side)
        boxes = fr._scene_boxes(tl, sc, data, on, xs, card, data["speaker"], side, tl.W, tl.H)
        t = sc["start"]
        while t < sc["end"]:
            k = max(0, bisect.bisect_right([x[0] for x in shots], t) - 1)
            name, (cx, cy, z), fit = shots[k][1]
            names.add(name)
            for zoom in (z, z + .05 + .045):                       # base, and with drift + beat punch
                for pan in (-tl.W * .0075, 0.0, tl.W * .0075):
                    x0, y0, w, h = fr._crop_box(cx + pan, cy, zoom, tl.W, tl.H, fit)
                    R = (x0, y0, x0 + w, y0 + h)
                    for key, b in boxes.items():
                        assert fr._inside(b, R, 1) or fr._apart(b, R, 1), (pace, si, name, key)
            t += .25
    if pace != "calm":                                                # variety kept: close-ups still happen
        assert {"wide", "card"} <= names and names & {"face", "react", "speaker"}


def test_sunny_moves_clear_of_cards():
    tl = _timeline("rapid", 6)
    for sc in tl.scenes:
        data, card, on, xs = _scene_layout(tl, sc)
        if not card:
            continue
        side = fr._sunny_side(tl, sc["seg"])
        assert side == "left"
        b = fr._scene_boxes(tl, sc, data, on, xs, card, data["speaker"], side, tl.W, tl.H)
        assert fr._apart(b["sunny"], b["card"]), "Sunny is covered by the card"


def test_segment_transition_is_quick_and_never_holds_a_blank_screen():
    tl = _timeline("lively", 6)
    fps = tl.fps
    closed = 0
    for g in range(len(tl.segments) - 1):
        a, b = tl.segments[g]["end"], tl.segments[g + 1]["start"]
        run = longest = 0
        for fi in range(int((a - .5) * fps), int((b + .5) * fps) + 1):
            k, _ = fr._transition(tl, fi / fps)
            run = run + 1 if k > .9 else 0
            longest = max(longest, run)
            closed += k > .999
        assert longest <= 3, f"iris (nearly) closed for {longest} frames between segments {g} and {g + 1}"
    assert closed >= 1                                     # the iris does still close (it's a real transition)
    # and real frames inside a gap are not blank for long
    a, b = tl.segments[1]["end"], tl.segments[2]["start"]
    blank = 0
    for fi in range(int(a * fps), int(b * fps) + 1):
        im = np.asarray(fr.render(tl, fi / fps).convert("RGB")).astype(float)
        blank += im.std(axis=(0, 1)).max() < 12
    assert blank <= 3


def test_thinking_calm_sleepy_faces_are_friendly():
    hs, up, tilt, lo, isc, psc, look = characters.EYE["thinking"]
    assert up == 0 and look[1] < -.5 and abs(look[0]) > .5          # eyes open, gazing up and to the side
    assert characters.BROW["thinking"][3] <= 0                       # no lowered (suspicious) brow
    assert characters.MOUTH["thinking"][0] > 0                       # small side smile, not a flat line
    for emo in ("calm", "sleepy"):
        assert characters.BROW[emo][0] <= 0 and characters.BROW[emo][3] <= 0, emo    # brows never knit/lowered
        assert characters.MOUTH[emo][0] > .3, emo                    # smiling
    assert characters.EYE["calm"][1] <= .1                           # calm is not half-lidded
    for cid in ("hoppy", "pip", "mimi"):
        a = np.asarray(characters.sprite(cid, 200, 0, "open", "thinking", "down"))
        b = np.asarray(characters.sprite(cid, 200, 0, "open", "happy", "down"))
        assert a.shape == b.shape and (a != b).any()


def test_template_script_reaches_target_length_with_varied_content():
    for band, minutes in (("preschool", 12), ("preschool", 15), ("toddler", 10), ("early", 12)):
        s = writer.template_script("numbers", "Counting with Pip and Friends", band, minutes, seed=2)
        dur = writer.template_seconds(s["segments"], band) / 60          # real-voice timing (calibrated)
        assert abs(dur - minutes) <= minutes * .1, (band, minutes, dur)
        assert episode.estimate_audio(s, 24)["duration"] / 60 >= minutes * .9            # the slow preview: never short
        kinds = [g["kind"] for g in s["segments"]]
        assert kinds[0] == "hello" and kinds[-1] == "goodbye"
        assert kinds.count("song") >= 2 and {"movement", "feelings", "story", "game"} <= set(kinds)
        story = next(g for g in s["segments"] if g["kind"] == "story")
        assert sum(sc["speaker"] == "hoppy" for sc in story["scenes"]) >= 5            # Hoppy is the star
        objects = {sc["card"]["object"] for g in s["segments"] if g["kind"] == "learn" for sc in g["scenes"]
                   if sc.get("card") and sc["card"].get("type") == "count"}
        assert len(objects) >= 3                                                        # different things to count
        m = psychology.analyze(s, band)
        assert not m["issues"], m["issues"]
        for g in s["segments"]:
            for sc in g["scenes"]:
                assert sc["speaker"] == "sunny" or sc["speaker"] in sc["cast"]
                assert "hoppy" in sc["cast"] and len(sc["cast"]) <= 3


def test_qa_length_is_honest_for_demo_scripts():
    from app import pipeline
    out = {"duration": 60.0, "flash": {"max_per_s": 0}, "engines": ["kokoro"], "W": 1920, "H": 1080, "fps": 24}
    ep = {"minutes": 12, "script": {"writer": "template"}, "safety": {"ok": True}, "critic": {"score": 9}}
    chk = pipeline.run_qa(ep, out, {})["checks"][0]
    assert chk["name"] == "Length (demo)" and chk["ok"] is False
    chk = pipeline.run_qa(ep, {**out, "duration": 12.2 * 60}, {})["checks"][0]
    assert chk["ok"] is True
    ai = {**ep, "script": {"writer": "ai"}}
    chk = pipeline.run_qa(ai, {**out, "duration": 4 * 60}, {})["checks"][0]
    assert chk["ok"] is False and chk["name"].startswith("Length")


def test_onnxruntime_telemetry_disabled():
    import app.tts  # noqa: F401
    assert os.environ.get("ORT_DISABLE_TELEMETRY") == "1"
