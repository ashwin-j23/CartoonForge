"""3D cartoon look: frame planning (no Blender needed) and one real Blender still (skipped without Blender)."""
from pathlib import Path

import pytest

from app.kids.writer import template_script
from app.render import three_d
from app.render.episode import estimate_audio
from app.render.frame import Timeline


def _tl():
    s = template_script("numbers", "Counting with Hoppy", "preschool", 6, seed=2)
    snd = estimate_audio(s, 24)
    return s, snd, Timeline(s, snd, 960, 540, 24, {"pace": "rapid", "art_style": "toy3d"})


def test_frame_states_cover_intro_scenes_and_outro():
    s, snd, tl = _tl()
    intro = three_d.frame_state(tl, 1.0)
    assert intro["mode"] == "intro" and any(c[0] == "hoppy" for c in intro["chars"])
    mid = three_d.frame_state(tl, snd["scenes"][3]["start"] + .3)
    assert mid["mode"] == "scene" and mid["chars"] and 1.0 <= mid["cam"][2] <= 3.0
    for c in mid["chars"]:
        assert len(c) == 12 and 0 <= c[1] <= 1 and c[4] in (
            "happy", "excited", "surprised", "thinking", "sad", "worried", "proud", "sleepy", "calm")
    outro = three_d.frame_state(tl, snd["outro_start"] + 1)
    assert outro["mode"] == "outro" and len(outro["chars"]) == 6


def test_cast_and_set_specs_are_json_ready():
    import json
    s, _, _ = _tl()
    s["characters"] = [{"id": "wolf", "name": "Wolf", "species": "wolf"}]
    cast = three_d.cast_specs(s)
    assert cast["hoppy"]["species"] == "frog" and cast["wolf"]["kind"] == "animal"
    json.dumps(cast)
    json.dumps(three_d.set_specs(s))


def test_auto_look_never_picks_3d():
    from app.render.styles import STYLES, for_band
    assert "toy3d" in STYLES
    assert all("toy3d" not in for_band(b) for b in ("toddler", "preschool", "early", "big"))


@pytest.mark.skipif(not three_d.available(), reason="Blender not installed (backend/tools/blender)")
def test_blender_still_renders(tmp_path: Path):
    from PIL import Image
    s, snd, _ = _tl()
    out = three_d.preview_still(s, {"pace": "calm", "channel_name": "CartoonForge"}, snd["scenes"][2]["start"] + .5,
                                tmp_path / "still.png")
    im = Image.open(out)
    assert im.size == (960, 540)
    px = im.convert("RGB").resize((8, 8)).getcolors(64)
    assert px and len(px) > 6                                   # a real picture, not a blank frame
