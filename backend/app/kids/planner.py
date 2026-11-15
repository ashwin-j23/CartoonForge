"""Planner: what the next episode should be.

Balances the mix (every kind of child: counting, stories, bedtime, science, feelings, the world…), learns from
analytics (categories with higher average view % get more slots, but never all of them — variety is what keeps a
family subscribed), follows the world calendar (festivals and awareness days from every continent) and never
repeats a topic.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from ..db import get_db
from ..llm.router import LLMError, complete_json
from ..settings import app_settings
from . import categories

# month, day, theme, category — fixed-date days kids everywhere can enjoy (movable feasts use the window below)
CALENDAR = [
    (1, 1, "Happy New Year around the world", "world"),
    (1, 24, "Lunar New Year: lanterns, dragons and dumplings", "world"),
    (2, 14, "Kindness cards: telling friends we care", "feelings"),
    (3, 8, "Amazing women inventors and explorers", "science"),
    (3, 14, "Holi: the festival of colours", "colors_shapes"),
    (3, 21, "Spring is here! Flowers, baby animals and rain", "animals"),
    (4, 7, "Healthy bodies: eat, sleep, play", "habits"),
    (4, 22, "Earth Day: caring for our planet", "science"),
    (5, 20, "World Bee Day: busy, buzzy bees", "animals"),
    (6, 5, "World Environment Day: trees, rivers and us", "science"),
    (6, 8, "World Oceans Day: friends under the sea", "animals"),
    (7, 20, "Moon landing day: let's go to the Moon", "space"),
    (7, 30, "Friendship Day: being a good friend", "feelings"),
    (8, 12, "World Elephant Day", "animals"),
    (9, 21, "International Day of Peace: kindness everywhere", "feelings"),
    (10, 4, "World Animal Day", "animals"),
    (10, 20, "Festivals of light: Diwali lamps and candles", "world"),
    (10, 31, "Friendly pumpkins and autumn leaves", "colors_shapes"),
    (11, 13, "World Kindness Day", "feelings"),
    (11, 20, "Children's Day: kids around the world", "world"),
    (11, 25, "Saying thank you: gratitude around the world", "feelings"),
    (12, 10, "Winter festivals around the world", "world"),
    (12, 21, "The longest night: stars, moon and sleepy animals", "bedtime"),
]

DEFAULT_WEIGHTS = {"numbers": 1.2, "abc": 1.2, "colors_shapes": 1.0, "animals": 1.3, "stories": 1.2, "bedtime": 1.0,
                   "science": 1.0, "space": 0.8, "dinosaurs": 0.8, "vehicles": 0.8, "habits": 0.9, "feelings": 1.0,
                   "world": 1.0, "music_move": 1.0, "puzzles": 0.6, "books": 1.3}


def upcoming(days: int = 45, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    for m, d, theme, cat in CALENDAR:
        for y in (today.year, today.year + 1):
            try:
                when = date(y, m, d)
            except ValueError:
                continue
            if 0 <= (when - today).days <= days:
                out.append({"date": when.isoformat(), "theme": theme, "category": cat})
    return sorted(out, key=lambda x: x["date"])


def used_topics() -> set[str]:
    return {t.get("topic", "").lower() for t in get_db().query("topics", limit=2000)}


def remember(topic: str, category: str, episode_id: str) -> None:
    get_db().insert("topics", {"topic": topic, "category": category, "episode_id": episode_id})


def weights() -> dict[str, float]:
    """Base mix x settings override x performance (avg view % per category, damped)."""
    s = app_settings()
    w = {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in (s.get("category_mix") or {}).items()}}
    perf = get_db().get_setting("category_perf", {}) or {}
    if perf:
        avg = sum(p["avg_pct"] for p in perf.values()) / len(perf) or 1
        for cid, p in perf.items():
            if cid in w and p.get("n", 0) >= 2:
                w[cid] *= max(0.6, min(1.6, (p["avg_pct"] / avg) ** 0.7))   # damped: variety always wins a slot
    recent = [e.get("category") for e in get_db().query("episodes", limit=6)]
    for i, cid in enumerate(recent):                     # don't run the same category back to back
        if cid in w:
            w[cid] *= 0.25 if i < 2 else 0.7
    return w


def next_episode(band_id: str | None = None, category_id: str | None = None, topic: str | None = None,
                 publish_on: date | None = None) -> dict:
    s = app_settings()
    band_id = band_id or s.get("age_band", "preschool")
    used = used_topics()
    when = publish_on or date.today() + timedelta(days=3)
    if not category_id and not topic:
        for ev in upcoming(14, when - timedelta(days=7)):
            if ev["theme"].lower() not in used and band_id in categories.get(ev["category"])["bands"]:
                return {"category": ev["category"], "topic": ev["theme"], "age_band": band_id, "why": f"Calendar: {ev['date']}"}
        if random.random() < float(s.get("trend_share", 0.6)):
            from . import trends
            tr = trends.next_trend(band_id)
            if tr:
                trends.mark_used(tr["id"], "")
                why = f"Trending ({tr['score']}): {tr.get('why', '')}"[:200]
                return {"category": tr["category"], "topic": tr["topic"], "age_band": tr.get("age_band") or band_id,
                        "why": why, "angle": tr.get("angle", "")}
    if not category_id:
        pool = [c for c in categories.for_band(band_id)] or categories.CATEGORIES
        w = weights()
        category_id = random.choices([c["id"] for c in pool], [w.get(c["id"], 1.0) for c in pool])[0]
    cat = categories.get(category_id)
    if band_id not in cat["bands"]:
        band_id = cat["bands"][min(1, len(cat["bands"]) - 1)]
    if not topic:
        fresh = [t for t in cat["topics"] if t.lower() not in used]
        topic = random.choice(fresh) if fresh else _new_topic(cat, band_id, used)
    return {"category": category_id, "topic": topic, "age_band": band_id, "why": "Balanced mix"}


def _new_topic(cat: dict, band_id: str, used: set[str]) -> str:
    try:
        data, _ = complete_json(
            "You plan episodes for a gentle educational kids channel watched worldwide. JSON only.",
            f"Category: {cat['name']}. Ages: {band_id}. Already made: {sorted(used)[-60:]}.\n"
            "Suggest 8 NEW episode topics (evergreen, globally relatable, concrete, child-safe). "
            "Return {\"topics\": [str]}", temperature=0.9, max_tokens=800)
        for t in data.get("topics") or []:
            if str(t).lower() not in used:
                return str(t)[:90]
    except (LLMError, ValueError):
        pass
    return random.choice(cat["topics"]) + f" (part {len([u for u in used if cat['topics'][0].lower()[:12] in u]) + 2})"
