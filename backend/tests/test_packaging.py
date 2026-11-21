"""Packaging from the channel review: story first in titles, no branding, short thumb words, ~3 Shorts a week."""
from app import pipeline
from app.db import get_db
from app.kids import hashtags, meta
from app.llm import router
from app.render import episode as epr


def _script(cat="stories"):
    return {"category": cat, "age_band": "preschool", "topic": "The fox and the rooster", "title_idea": "The Clever Fox & the Rooster",
            "summary": "A sly fox tries to trick a rooster at bedtime.", "segments": [], "key_words": ["fox"], "lesson": "think first"}


def test_title_drops_channel_name_and_fallback_leads_with_the_story(monkeypatch):
    def fake(*a, **k):
        return {"title": "The Clever Fox & the Rooster 🦊 Bedtime Story for Kids | Hoppy Hop Hop", "tags": []}, None
    monkeypatch.setattr(meta, "complete_json", fake)
    m = meta.build(_script(), {"channel_name": "Hoppy Hop Hop"})
    assert m["title"] == "The Clever Fox & the Rooster 🦊 Bedtime Story"          # brand off, under 50 chars
    assert meta.fit_title("Colors & Shapes with Hoppy 🎨 Fun Preschool Learning for Toddlers and Kids") == \
        "Colors & Shapes with Hoppy 🎨"
    assert meta.fit_title("Why Is This Bigger? Counting Song for Preschoolers and Toddlers Too") == "Why Is This Bigger? Counting Song for Preschoolers"
    assert meta.fit_title("Learn Colors with Mimi") == "Learn Colors with Mimi"
    assert m["playlist"].startswith("📖 Fables & Bedtime Stories")

    def boom(*a, **k):
        raise router.LLMError("down")
    monkeypatch.setattr(meta, "complete_json", boom)
    t = meta.build(_script(), {"channel_name": "Hoppy Hop Hop"})["title"]
    assert t.startswith("The Clever Fox & the Rooster") and "Hoppy Hop Hop" not in t


def test_thumb_words_at_most_three_and_short_caption_never_ends_on_and(tmp_path):
    assert len(epr._thumb_words("x", [], "Count All The Apples Today").split()) <= 3
    from PIL import Image
    out = epr.short_caption("The Clever Fox and the Rooster", tmp_path / "c.png")
    assert out and Image.open(out).width == 1080
    assert epr.short_caption("#shorts", tmp_path / "d.png") is None


def test_milestone_topics_get_their_hashtags():
    body = {"t": "potty potty potty, clean up clean up tidy up"}
    tags = hashtags.pick("habits", body, n=8)
    assert "#PottyTraining" in tags and "#CleanUpSong" in tags


def test_about_a_short_a_day_never_a_repeat_clip():
    db = get_db()
    for e in db.query("episodes", eq={"kind": "short"}, limit=500):
        db.update("episodes", e["id"], {"kind": "short-old"})
    assert pipeline.shorts_wanted("a") == 4                      # first episode of the week: 4 cuts
    for _ in range(4):
        db.insert("episodes", {"kind": "short", "parent_id": "a"})
    assert pipeline.shorts_wanted("b") == 3                      # second episode: 3 more = 7 that week
    two = db.insert("episodes", {"kind": "episode", "song_regions": [{"start": 100, "end": 190}],
                                 "timeline": [{"kind": "story", "start": 20, "end": 60}]})
    assert pipeline.shorts_wanted(two["id"]) == 2                # only 2 distinct cuts -> 2 Shorts, no duplicate
    p = {"song_regions": [{"start": 100, "end": 190}], "timeline": [{"kind": "story", "start": 20, "end": 60},
                                                                     {"kind": "game", "start": 110, "end": 150}]}
    cuts = pipeline._short_cuts(p)
    assert cuts[0] == (100, 158, True) and cuts[1] == (20, 60, False) and len(cuts) == 2   # starts on the beat


def test_hook_is_four_lines_with_no_roll_call():
    from app.kids import writer
    cat = {"lead": "hoppy"}
    raw = [{"speaker": "hoppy", "text": "Look, a dinosaur bone! Can you find it?"},
           {"speaker": "sunny", "text": "Hello, little sprouts!"},
           {"speaker": "pip", "text": "Hi! I'm Pip!"},
           {"speaker": "mimi", "text": "And I'm Mimi!"},
           {"speaker": "sunny", "text": "Let's dig it up together!"},
           {"speaker": "bo", "text": "Dig, dig, dig!"},
           {"speaker": "hoppy", "text": "What will we find?"}]
    out = [sc["text"] for sc in writer.clean_scenes(raw, {"kind": "hello"}, cat)]
    assert out == ["Look, a dinosaur bone! Can you find it?", "Let's dig it up together!", "Dig, dig, dig!",
                   "What will we find?"]


def test_long_opening_is_cut_before_upload(tmp_path):
    import subprocess
    from app import pipeline
    src = tmp_path / "ep.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=40", "-f", "lavfi",
                    "-i", "anullsrc=r=22050", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)], check=True)
    tl = [{"kind": "hello", "title": "Hello!", "start": 0, "end": 30}, {"kind": "story", "title": "Into the Woods", "start": 30, "end": 45},
          {"kind": "song", "title": "Song", "start": 45, "end": 60}, {"kind": "goodbye", "title": "Bye", "start": 60, "end": 75}]
    desc = "Hook.\n\n0:00 Hello!\n0:30 Into the Woods\n0:45 Song\n\nMore."
    out, new, cut = pipeline.trim_opening(src, tl, desc)
    assert cut == 30 and out != src and out.exists()
    assert "Hello!" not in new and "0:00 Into the Woods\n0:15 Song\n0:30 Bye" in new
    short_tl = [{**tl[0], "end": 12}, {**tl[1], "start": 12}]
    assert pipeline.trim_opening(src, short_tl, desc) == (src, desc, 0.0)       # a real hook stays


def test_3d_falls_back_to_2d_when_this_machine_is_too_slow(monkeypatch, tmp_path):
    from app.render import episode as epr, three_d
    from app.kids.writer import template_script
    monkeypatch.setattr(three_d, "available", lambda: True)
    monkeypatch.setattr(three_d, "seconds_per_frame", lambda job, wd, n=4: 7.0)      # a CPU-only runner
    seen = []
    monkeypatch.setattr(epr, "_size", lambda s: (_ for _ in ()).throw(RuntimeError(f"2D:{s.get('_style')}")))
    s = template_script("numbers", "Counting", "preschool", 3, seed=1)
    try:
        epr.render(s, {"_style": "toy3d", "render_3d_max_minutes": 120}, tmp_path, log=seen.append)
    except RuntimeError as e:
        assert str(e) == "2D:classic"                    # went on to the 2D renderer
    assert any("rendering in the classic 2D look" in m for m in seen)
    monkeypatch.setattr(three_d, "seconds_per_frame", lambda job, wd, n=4: 0.2)      # a GPU: 3D goes ahead
    monkeypatch.setattr(three_d, "render_video", lambda *a, **k: {"ok": "3d"})
    assert epr.render(s, {"_style": "toy3d"}, tmp_path, log=seen.append) == {"ok": "3d"}
    three_d.check_speed(s, {"render_3d_max_minutes": 120}, tmp_path, seen.append)    # fast enough: no raise
