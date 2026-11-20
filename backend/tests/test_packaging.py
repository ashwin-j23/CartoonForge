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
    assert m["title"] == "The Clever Fox & the Rooster 🦊 Bedtime Story for Kids"
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


def test_about_three_shorts_a_week():
    db = get_db()
    for e in db.query("episodes", eq={"kind": "short"}, limit=500):
        db.update("episodes", e["id"], {"kind": "short-old"})
    assert pipeline.shorts_wanted("a") == 2                      # first episode of the week: song + lively bit
    db.insert("episodes", {"kind": "short", "parent_id": "a"})
    db.insert("episodes", {"kind": "short", "parent_id": "a"})
    assert pipeline.shorts_wanted("b") == 1                      # second episode: one more = 3 that week
    p = {"song_regions": [{"start": 100, "end": 190}], "timeline": [{"kind": "story", "start": 20, "end": 60},
                                                                     {"kind": "game", "start": 110, "end": 150}]}
    cuts = pipeline._short_cuts(p)
    assert cuts[0] == (100, 158, True) and cuts[1] == (20, 60, False) and len(cuts) == 2   # starts on the beat
