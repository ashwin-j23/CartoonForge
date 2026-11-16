"""Titles/tags must not promise a skill (colors, counting, ABC...) the episode doesn't contain."""
from app.kids.meta import unfounded


def _script(*lines):
    return {"segments": [{"title": "Frogs", "scenes": [{"text": t} for t in lines]}]}


def test_flags_promises_the_episode_does_not_keep():
    frogs = _script("Hop like a frog!", "Frogs live by the river.")
    assert unfounded("Why Do Frogs Jump? Learn Colors | Counting Song", frogs) == ["colors", "counting"]
    assert unfounded("Jungle Animals for Toddlers", frogs) == []


def test_allows_promises_the_episode_keeps():
    s = _script("What color is the frog? Green!", "Let's count: one, two, three frogs.")
    assert unfounded("Learn Colors and Counting with Frogs", s) == []
