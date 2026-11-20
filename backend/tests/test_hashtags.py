"""Hashtags parents search, only when true for the video; tags never cut or misspell the brand."""
from datetime import date

from app.kids import hashtags


def test_season_only_when_the_episode_is_about_it():
    xmas = {"t": "Bo bakes Christmas cookies for a Christmas party"}
    assert hashtags.pick("habits", xmas, today=date(2026, 12, 1))[0] == "#ChristmasSongsForKids"
    assert "#ChristmasSongsForKids" not in hashtags.pick("habits", {"t": "sharing apples"}, today=date(2026, 12, 1))
    assert "#ChristmasSongsForKids" not in hashtags.pick("habits", xmas, today=date(2026, 7, 1))


def test_three_focused_category_first_shorts_last():
    tags = hashtags.pick("colors_shapes", {"t": "red"}, short=True)
    assert tags[0] == "#LearnColors" and tags[-1] == "#Shorts" and len(tags) == 3
    assert hashtags.pick("bedtime", {"t": "sleep"}) == ["#BedtimeStory", "#BedtimeStoriesForKids", "#Lullaby"]
    assert not any("_" in t for t in tags)                      # no '#colors_shapes'


def test_tags_drop_typos_and_long_ones():
    got = hashtags.clean_tags(["Hoopy Hop Hop", "hoping hop hop", "kids songs", "x" * 45, "Kids Songs"], "Hoppy Hop Hop")
    assert got == ["Hoppy Hop Hop", "kids songs"]
