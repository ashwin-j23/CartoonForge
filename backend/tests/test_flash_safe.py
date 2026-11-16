"""Segment transitions are flash-safe: rendered at the QA sampling rate, day<->night switches stay far under 3/s."""
import numpy as np

from app.kids.writer import template_script
from app.render import frame as fr
from app.render.episode import estimate_audio, flash_check


def test_transitions_bright_to_night_are_flash_safe():
    s = template_script("numbers", "Counting with Hoppy", "preschool", 4, seed=2)
    for i, seg in enumerate(s["segments"]):
        seg["set"] = ["meadow", "night"][i % 2]
    snd = estimate_audio(s, 24)
    tl = fr.Timeline(s, snd, 192, 108, 24, {"pace": "calm", "art_style": "classic", "channel_name": "Hoppy Hop Hop"})
    switches = fr._switches(tl)
    assert switches
    for m, _ in switches:
        lum = [float(np.asarray(fr.render(tl, m + k / 12).convert("RGB").resize((32, 18))).mean()) for k in range(-12, 13)]
        assert flash_check(lum, 12)["max_per_s"] <= 1, m


def test_iris_closes_onto_the_scene_colour():
    from PIL import Image
    bright = Image.new("RGB", (64, 36), (200, 220, 240))
    out = fr._iris(bright.copy(), 1.0)
    assert abs(np.asarray(out).mean() - np.asarray(bright).mean()) < 30      # was a dark plum (~70 brightness)


def test_page_turn_paper_follows_the_scene():
    from PIL import Image
    night = Image.new("RGB", (64, 36), (30, 35, 80))
    out = fr._page_turn(night.copy(), 1.0)
    assert np.asarray(out).mean() < 140                                     # dusky paper at night, not bright cream
    day = Image.new("RGB", (64, 36), (210, 230, 245))
    assert np.asarray(fr._page_turn(day.copy(), 1.0)).mean() > 200          # cream page by day
