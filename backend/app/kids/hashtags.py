"""Hashtags and tags that parents actually search, and that are TRUE for the video.

YouTube shows the first 3 hashtags above the title (each links to a results page) and treats unrelated or
misleading hashtags as a policy problem, so: the 3 most specific, searchable ones go first, nothing the episode
doesn't contain, no competitor brand names. Phrases come from YouTube autocomplete research (Nov 2026,
research_notes/Kids channel growth strategy/packaging_and_hashtags.md).
"""
from __future__ import annotations

import json
import re
from datetime import date

BRAND = "#HoppyHopHop"

# category -> hashtags in priority order (first ones show above the title)
CATEGORY = {
    "numbers": ["#CountingSong", "#LearnNumbers", "#PreschoolLearning"],
    "abc": ["#ABCSong", "#Phonics", "#LearnABC"],
    "colors_shapes": ["#LearnColors", "#ShapesForKids", "#ToddlerLearning"],
    "animals": ["#AnimalSounds", "#AnimalsForKids", "#ToddlerLearning"],
    "bedtime": ["#BedtimeStory", "#BedtimeStoriesForKids", "#Lullaby"],
    "books": ["#BedtimeStoriesForKids", "#StoryTime", "#KidsStories"],
    "stories": ["#StoryTime", "#KidsStories", "#BedtimeStoriesForKids"],
    "music_move": ["#KidsSongs", "#SongsForToddlers", "#DanceForKids"],
    "habits": ["#HealthyHabits", "#GoodManners", "#ToddlerLearning"],
    "feelings": ["#FeelingsForKids", "#CalmDownSong", "#SocialEmotionalLearning"],
    "vehicles": ["#TrucksForKids", "#VehiclesForKids", "#ToddlerLearning"],
    "dinosaurs": ["#DinosaursForKids", "#DinosaurSong", "#PreschoolLearning"],
    "world": ["#KidsLearning", "#CulturesForKids", "#PreschoolLearning"],
    "science": ["#ScienceForKids", "#KidsLearning", "#PreschoolLearning"],
    "space": ["#SpaceForKids", "#PlanetsForKids", "#KidsLearning"],
    "puzzles": ["#KidsRiddles", "#KidsLearning", "#PreschoolLearning"],
}
GENERAL = ["#LearningVideosForToddlers", "#PreschoolLearning", "#KidsLearning", "#EducationalVideosForKids"]

# topic words in the script -> extra specific hashtags (only added when the script really has them)
TOPICAL = [
    (("share", "sharing"), "#SharingIsCaring"),
    (("thank you", "thankful", "grateful"), "#ThankYouSong"),
    (("brush", "teeth"), "#BrushYourTeeth"),
    (("sing", "song"), "#SingAlong"),
    (("clean up", "tidy up", "tidy"), "#CleanUpSong"),
    (("potty",), "#PottyTraining"),
    (("bedtime routine", "time for bed", "bath, brush"), "#BedtimeRoutine"),
    (("please", "excuse me", "manners"), "#GoodManners"),
]

# (first month-day, last month-day, words the script must contain, hashtags)
SEASONS = [
    ("11-15", "12-26", ("christmas", "santa", "reindeer"), ["#ChristmasSongsForKids", "#ChristmasForKids"]),
    ("12-01", "02-28", ("snow", "winter", "snowman", "mitten"), ["#WinterSongsForKids", "#SnowmanSong"]),
    ("12-26", "01-06", ("new year", "countdown"), ["#HappyNewYearForKids"]),
    ("10-20", "11-28", ("thanksgiving", "thankful"), ["#ThanksgivingForKids"]),
    ("10-01", "10-31", ("halloween", "pumpkin"), ["#PumpkinSong"]),
]


def _in_window(today: date, a: str, b: str) -> bool:
    md = today.strftime("%m-%d")
    return a <= md <= b if a <= b else (md >= a or md <= b)       # windows may wrap the new year


def _text(script: dict | None) -> str:
    return json.dumps(script or {}, ensure_ascii=False).lower()


def pick(category: str, script: dict | None, short: bool = False, today: date | None = None, n: int = 5) -> list[str]:
    """Ordered, de-duplicated hashtags: season (if the episode is about it) + category + topic + general + brand."""
    body = _text(script)
    today = today or date.today()
    out: list[str] = []
    for a, b, words, tags in SEASONS:
        if _in_window(today, a, b) and sum(body.count(w) for w in words) >= 2:
            out += tags
    out += CATEGORY.get(category, [])
    out += [t for words, t in TOPICAL if sum(body.count(w) for w in words) >= 3]   # the topic, not a passing word
    out += GENERAL
    seen, res = set(), []
    for t in out:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            res.append(t)
    res = res[: n - (2 if short else 1)] + [BRAND] + (["#Shorts"] if short else [])
    return res


def line(category: str, script: dict | None, short: bool = False, today: date | None = None) -> str:
    return " ".join(pick(category, script, short, today))


def clean_tags(tags: list, channel: str, limit_chars: int = 480) -> list[str]:
    """Tags: drop (never cut) over-long ones, drop misspellings of the channel name, keep the real name once,
    stay under YouTube's 500-character total."""
    name = channel.lower()
    squash = lambda s: re.sub(r"[^a-z]", "", s.lower())   # noqa: E731
    out, seen, total = [channel], {name}, len(channel)
    for t in tags or []:
        t = re.sub(r"\s+", " ", str(t)).strip().strip("#")
        k = t.lower()
        if not t or len(t) > 40 or k in seen:
            continue
        # 'Hoopy Hop Hop', 'hoping hop hop': close to the brand but not it -> a typo, not a search phrase
        last = " ".join(name.split()[-2:])                 # 'hop hop'
        if k != name and (_close(squash(t), squash(channel)) or (len(name.split()) > 2 and k.endswith(last)
                                                                  and len(k.split()) == len(name.split()))):
            continue
        if total + len(t) + 1 > limit_chars:
            break
        out.append(t)
        seen.add(k)
        total += len(t) + 1
    return out


def _close(a: str, b: str) -> bool:
    if not a or not b or abs(len(a) - len(b)) > 3:
        return False
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() >= .8
