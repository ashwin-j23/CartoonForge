"""Trend analyser: which children's topics are rising RIGHT NOW, turned into episode ideas.

Signals (all free; the YouTube one needs YOUTUBE_API_KEY, a plain API key):
  1. YouTube search autocomplete  — what parents are typing this week, per country (no key, no quota)
  2. YouTube hot videos           — kids videos from the last 14 days ranked by views per day, per country
                                     (search.list: 1 unit, 100 calls/day bucket; we use ~24 a scan)
  3. Wikipedia pageviews          — kid-interest subjects whose views jumped vs the previous 4 weeks
  4. The world calendar           — festivals and awareness days in the next 3 weeks (planner.CALENDAR)
The Analyst (AI) merges them into ranked ideas mapped to our categories and age bands, with an ORIGINAL angle:
a trend about a famous show becomes an episode about its underlying subject (never its characters or brand).
"""
from __future__ import annotations

import re
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import httpx

from ..db import get_db
from ..llm.router import LLMError, complete_json
from ..settings import app_settings, secret
from . import categories, planner, safety

SEEDS = ["nursery rhymes", "kids songs", "songs for kids", "learn colors", "learning videos for toddlers",
         "bedtime story", "story for kids", "counting song", "abc song", "animals for kids", "dinosaur for kids",
         "kids cartoon", "phonics", "baby songs", "science for kids", "space for kids"]
REGIONS = ["US", "IN", "GB", "BR", "ID", "PH", "MX", "NG"]
WIKI_WATCH = ["Dinosaur", "Tyrannosaurus", "Shark", "Whale", "Octopus", "Elephant", "Lion", "Penguin", "Butterfly",
              "Bee", "Volcano", "Rainbow", "Moon", "Sun", "Mars", "Solar_System", "Planet", "Astronaut", "Rocket",
              "Snow", "Rain", "Tornado", "Ocean", "Rainforest", "Desert", "Fire_engine", "Train", "Airplane",
              "Diwali", "Christmas", "Halloween", "Easter", "Chinese_New_Year", "Eid_al-Fitr", "Hanukkah",
              "Holi", "Thanksgiving", "Earth_Day", "Pumpkin", "Autumn", "Spring_(season)", "Football", "Olympic_Games"]
# Wikimedia requires a descriptive User-Agent with a contact URL, and blocks vague ones after the first call
UA = {"User-Agent": "CartoonForgeTrendBot/1.0 (https://github.com/cartoonforge/cartoonforge; trends) python-httpx"}


# ---------------------------------------------------------------- signal 1: autocomplete
def autocomplete(seed: str, region: str = "US", lang: str = "en") -> list[str]:
    r = httpx.get("https://suggestqueries.google.com/complete/search", timeout=15, headers=UA,
                  params={"client": "firefox", "ds": "yt", "q": seed, "hl": lang, "gl": region})
    r.raise_for_status()
    data = r.json()
    return [s for s in (data[1] if len(data) > 1 else []) if isinstance(s, str)]


def suggest_signals(regions: list[str] | None = None) -> list[dict]:
    """Phrases that show up across seeds and countries = what many parents are searching now."""
    count, where = Counter(), {}
    for region in regions or REGIONS[:4]:
        for seed in SEEDS:
            try:
                for s in autocomplete(seed, region):
                    s = s.lower().strip()
                    if s == seed or len(s) < 4:
                        continue
                    count[s] += 1
                    where.setdefault(s, set()).add(region)
            except httpx.HTTPError:
                continue
            time.sleep(0.15)                       # be polite
    return [{"phrase": p, "hits": n, "regions": sorted(where[p]), "source": "youtube_search"}
            for p, n in count.most_common(80)]


# ---------------------------------------------------------------- signal 2: hot videos
def hot_videos(regions: list[str] | None = None, per_region: int = 3) -> list[dict]:
    key = secret("YOUTUBE_API_KEY")
    if not key:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(timespec="seconds").replace("+00:00", "Z")
    out, ids = [], {}
    for region in regions or REGIONS:
        for seed in SEEDS[:per_region]:
            try:
                r = httpx.get("https://www.googleapis.com/youtube/v3/search", timeout=20, params={
                    "key": key, "part": "snippet", "q": seed, "type": "video", "order": "viewCount", "maxResults": 15,
                    "publishedAfter": since, "regionCode": region, "safeSearch": "strict", "videoDuration": "medium"})
                r.raise_for_status()
            except httpx.HTTPError:
                continue
            for it in r.json().get("items", []):
                vid = it["id"].get("videoId")
                if vid and vid not in ids:
                    ids[vid] = {"id": vid, "title": it["snippet"]["title"], "channel": it["snippet"]["channelTitle"],
                                "published": it["snippet"]["publishedAt"], "region": region}
    keys = list(ids)
    for i in range(0, len(keys), 50):
        try:
            r = httpx.get("https://www.googleapis.com/youtube/v3/videos", timeout=20,
                          params={"key": key, "part": "statistics", "id": ",".join(keys[i:i + 50])})
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        for v in r.json().get("items", []):
            d = ids[v["id"]]
            views = int(v.get("statistics", {}).get("viewCount", 0))
            age = max(1.0, (datetime.now(timezone.utc) - datetime.fromisoformat(d["published"].replace("Z", "+00:00"))).days)
            out.append({**d, "views": views, "views_per_day": round(views / age), "source": "youtube_hot"})
    return sorted(out, key=lambda x: -x["views_per_day"])[:60]


# ---------------------------------------------------------------- signal 3: Wikipedia pageviews
def wiki_rising() -> list[dict]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=35)
    out = []
    for art in WIKI_WATCH:
        url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
               f"{art}/daily/{start:%Y%m%d}00/{end:%Y%m%d}00")
        r = None
        for attempt in range(3):                 # Wikimedia throttles fast clients (403/429): slow down, retry
            try:
                r = httpx.get(url, timeout=15, headers=UA)
            except httpx.HTTPError:
                r = None
            if r is not None and r.status_code == 200:
                break
            time.sleep(2.0 * (attempt + 1))
        time.sleep(0.8)
        if r is None or r.status_code != 200:
            continue
        views = [x["views"] for x in r.json().get("items", [])]
        if len(views) < 30:
            continue
        recent, before = sum(views[-7:]) / 7, sum(views[:-7]) / max(1, len(views) - 7)
        ratio = recent / max(1.0, before)
        out.append({"subject": art.replace("_", " "), "ratio": round(ratio, 2), "daily": round(recent),
                    "source": "wikipedia"})
    return sorted(out, key=lambda x: -x["ratio"])


# ---------------------------------------------------------------- analysis
_CAT_WORDS = {
    "numbers": ["count", "number", "123", "math"], "abc": ["abc", "alphabet", "phonics", "letter", "spell"],
    "colors_shapes": ["color", "colour", "shape"], "animals": ["animal", "shark", "whale", "lion", "elephant", "farm", "zoo",
                                                            "bird", "bug", "penguin", "octopus", "butterfly", "bee"],
    "stories": ["story", "fable", "tale"], "bedtime": ["bedtime", "sleep", "lullaby", "goodnight"],
    "science": ["science", "volcano", "rainbow", "weather", "experiment", "tornado", "rain"],
    "space": ["space", "planet", "moon", "rocket", "astronaut", "mars", "solar"], "dinosaurs": ["dinosaur", "t rex", "tyrannosaurus"],
    "vehicles": ["truck", "car", "train", "plane", "fire engine", "tractor", "excavator", "airplane"],
    "habits": ["brush", "wash", "potty", "eat", "dress", "routine", "bath"], "feelings": ["feeling", "emotion", "friend", "kind", "share"],
    "world": ["diwali", "christmas", "halloween", "easter", "eid", "hanukkah", "holi", "new year", "country", "world", "thanksgiving"],
    "music_move": ["dance", "song", "rhyme", "music", "freeze"], "books": ["book", "read aloud", "fairy tale"],
}


def guess_category(text: str) -> str:
    low = text.lower()
    best = max(_CAT_WORDS, key=lambda c: sum(w in low for w in _CAT_WORDS[c]))
    return best if any(w in low for w in _CAT_WORDS[best]) else "animals"


def _brand_free(text: str) -> bool:
    return not any(i["rule"] == "brands" for i in safety.check_text(text))


def analyse(suggest: list[dict], hot: list[dict], wiki: list[dict], upcoming: list[dict]) -> list[dict]:
    """Merge signals into ranked, original, safe episode ideas."""
    s = app_settings()
    band = s.get("age_band", "preschool")
    cats = {c["id"]: c["name"] for c in categories.CATEGORIES}
    try:
        data, _ = complete_json(
            "You are the trends analyst of a gentle educational kids' YouTube channel watched worldwide. You turn raw "
            "search/view signals into ORIGINAL episode ideas. Never copy a show, brand or character: if a trend is a "
            "famous show, make an idea about its underlying subject (a trending 'dog family cartoon' -> an original "
            "episode about puppies and sharing). Child-safe only. JSON only.",
            f"Today: {date.today().isoformat()}. Main audience: {band}.\nOur categories: {cats}\n"
            f"SEARCH AUTOCOMPLETE (phrase, hits across seeds/countries): {[(x['phrase'], x['hits'], x['regions']) for x in suggest[:50]]}\n"
            f"HOT KIDS VIDEOS last 14 days (title, views/day, country): {[(x['title'][:70], x['views_per_day'], x['region']) for x in hot[:35]]}\n"
            f"WIKIPEDIA rising subjects (subject, this week vs before): {[(x['subject'], x['ratio']) for x in wiki[:15]]}\n"
            f"UPCOMING WORLD DAYS: {[(x['date'], x['theme']) for x in upcoming]}\n\n"
            "Return {\"ideas\": [12 items, best first: {\"topic\": str (episode topic, max 70 chars, original), "
            "\"category\": one of our category ids, \"age_band\": toddler|preschool|early|big, \"score\": 0-100 "
            "(trend strength x fit for us), \"rising\": true|false, \"evergreen\": true|false, "
            "\"why\": str (which signals, in one line), \"angle\": str (what makes OUR version special)}]}",
            temperature=0.5, max_tokens=3500)
        ideas = data.get("ideas") or []
    except (LLMError, ValueError):
        ideas = _heuristic(suggest, hot, wiki, upcoming)
    out = []
    for it in ideas:
        topic = str(it.get("topic", "")).strip()[:90]
        if not topic or not _brand_free(topic) or any(i["level"] == "block" for i in safety.check_text(topic)):
            continue
        cat = it.get("category") if it.get("category") in categories.BY_ID else guess_category(topic)
        b = it.get("age_band") if it.get("age_band") in ("toddler", "preschool", "early", "big") else band
        if b not in categories.get(cat)["bands"]:
            b = categories.get(cat)["bands"][min(1, len(categories.get(cat)["bands"]) - 1)]
        out.append({"topic": topic, "category": cat, "age_band": b, "score": int(it.get("score", 50) or 50),
                    "rising": bool(it.get("rising")), "evergreen": bool(it.get("evergreen")),
                    "why": str(it.get("why", ""))[:200], "angle": str(it.get("angle", ""))[:200]})
    return sorted(out, key=lambda x: -x["score"])


def _heuristic(suggest, hot, wiki, upcoming) -> list[dict]:
    """No AI key: rank brand-free autocomplete phrases + rising Wikipedia subjects + upcoming days."""
    ideas = []
    for x in suggest[:30]:
        if _brand_free(x["phrase"]):
            ideas.append({"topic": x["phrase"].title(), "category": guess_category(x["phrase"]), "score": min(95, 40 + x["hits"] * 6),
                          "rising": True, "why": f"Searched in {', '.join(x['regions'])}", "angle": ""})
    past = {"halloween": (10, 31), "christmas": (12, 25), "diwali": (10, 20), "easter": (4, 5), "thanksgiving": (11, 26),
            "holi": (3, 14), "hanukkah": (12, 14), "chinese new year": (1, 29), "earth day": (4, 22)}
    today = date.today()
    for w in wiki[:8]:
        md = past.get(w["subject"].lower())
        if md and 0 < (today - date(today.year, *md)).days < 300:
            continue                                  # interest spiked because the day just happened
        if w["ratio"] > 1.25:
            ideas.append({"topic": f"All about the {w['subject']}", "category": guess_category(w["subject"]),
                          "score": min(90, int(40 + (w["ratio"] - 1) * 60)), "rising": True,
                          "why": f"Wikipedia interest x{w['ratio']} this week", "angle": ""})
    for u in upcoming[:3]:
        ideas.append({"topic": u["theme"], "category": u["category"], "score": 70, "rising": True,
                      "why": f"World day {u['date']}", "angle": ""})
    return ideas


# ---------------------------------------------------------------- scan + store
def scan(log=print) -> dict:
    t0 = time.time()
    sug = suggest_signals()
    log(f"Trends: {len(sug)} search phrases")
    hot = hot_videos()
    log(f"Trends: {len(hot)} hot kids videos" + ("" if secret("YOUTUBE_API_KEY") else " (add YOUTUBE_API_KEY for this signal)"))
    wiki = wiki_rising()
    up = planner.upcoming(21)
    ideas = analyse(sug, hot, wiki, up)
    db = get_db()
    for old in db.query("trends", eq={"used": False}, limit=500):
        db.delete("trends", old["id"])                   # replace last scan's unused ideas
    for it in ideas:
        db.insert("trends", {**it, "used": False})
    snapshot = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "suggest": sug[:40],
                "hot": hot[:30], "wiki": wiki[:20], "upcoming": up, "ideas": len(ideas),
                "seconds": round(time.time() - t0, 1)}
    db.set_setting("trends_snapshot", snapshot)
    log(f"Trends: {len(ideas)} ideas ready")
    return snapshot


def next_trend(band: str | None = None) -> dict | None:
    db = get_db()
    used = planner.used_topics()
    for t in db.query("trends", eq={"used": False}, order="score", desc=True, limit=50):
        if t["topic"].lower() in used:
            continue
        if band and band not in categories.get(t["category"])["bands"]:
            continue
        return t
    return None


def mark_used(tid: str, episode_id: str) -> None:
    try:
        get_db().update("trends", tid, {"used": True, "episode_id": episode_id})
    except KeyError:
        pass


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()
