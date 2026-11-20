"""YouTube metadata: honest, parent-friendly titles, chapters from the real timeline, translations.

Parents search and pick for the under-8s, so titles say plainly what the child gets ("Learn to Count to 10 |
Songs & Games for Toddlers"), never clickbait. Chapters let parents jump to the song their child loves.
"""
from __future__ import annotations

import re

from ..llm.router import LLMError, complete_json
from . import categories, hashtags, languages, psychology, safety
from .growth import SEO_KEYWORDS

# Search phrases that promise specific content -> words that must appear somewhere in the script for the promise to
# be true. Stops titles like "Learn Colors" on an episode about frogs (the model copies example phrases).
_PROMISES = {
    r"\bcolou?rs?\b": ("color", "colour", "red", "blue", "yellow", "green", "purple", "orange"),
    r"\bshapes?\b": ("shape", "circle", "square", "triangle"),
    r"\bcount(ing)?\b|\bnumbers?\b": ("count", "number", "how many"),
    r"\babc\b|\bphonics\b|\balphabet\b|\bletters?\b": ("letter", "abc", "alphabet", "phonics"),
    r"\bbedtime\b|\bsleep\b|\blullaby\b": ("sleep", "bed", "night", "goodnight", "lullaby"),
    r"\banimal sounds?\b": ("sound", "moo", "roar", "quack", "oink", "baa", "woof", "ribbit"),
    r"\bdinosaurs?\b": ("dinosaur",),
    r"\bteeth\b": ("teeth", "tooth"),
    r"\bfeelings?\b|\bemotions?\b": ("feel", "happy", "sad", "angry", "emotion"),
    r"\bnursery rhymes?\b": ("rhyme", "song", "sing"),
}


# category -> (the phrase parents search, the searchable series playlist it lands in)
SEARCH = {
    "bedtime": ("Bedtime Story for Toddlers", "🌙 Bedtime Stories for Toddlers | Calm Sleep Stories"),
    "stories": ("Bedtime Story for Kids", "📖 Fables & Bedtime Stories for Kids | Aesop & Folk Tales"),
    "books": ("Story Time for Kids", "📚 Storybook Classics Read Aloud for Kids"),
    "music_move": ("Nursery Rhymes & Kids Songs", "🎵 Nursery Rhymes & Sing-Alongs for Toddlers"),
    "habits": ("Healthy Habits for Toddlers", "🪥 Toddler Routines: Clean Up, Potty, Bath & Bedtime"),
    "feelings": ("Sharing & Manners for Toddlers", "💛 Sharing, Manners & Feelings for Toddlers"),
    "colors_shapes": ("Learn Colors for Toddlers", "🌈 Learn Colors & Shapes for Toddlers"),
    "numbers": ("Counting Song for Toddlers", "🔢 Counting Songs & Numbers for Toddlers"),
    "abc": ("ABC Song for Toddlers", "🔤 ABC Songs & Phonics for Toddlers"),
    "animals": ("Animal Sounds for Toddlers", "🐘 Animal Songs & Sounds for Toddlers"),
    "vehicles": ("Trucks & Vehicles for Kids", "🚒 Trucks, Trains & Vehicles for Kids"),
    "dinosaurs": ("Dinosaurs for Kids", "🦕 Dinosaur Songs & Stories for Kids"),
}


def _script_text(script: dict) -> str:
    import json
    return json.dumps(script, ensure_ascii=False).lower()


def unfounded(text: str, script: dict) -> list[str]:
    """Search phrases in `text` that promise something the episode doesn't contain."""
    body, low = _script_text(script), str(text or "").lower()
    return [m.group(0) for pat, need in _PROMISES.items() if (m := re.search(pat, low)) and not any(w in body for w in need)]


def _ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}" if sec < 3600 else f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def chapters(timeline: list[dict]) -> str:
    """'0:00 Hello!' lines. YouTube needs the first at 0:00, 3+ chapters, each at least 10 s."""
    rows, last = [], -99.0
    for seg in timeline:
        t = 0.0 if not rows else seg["start"]
        if t - last < 10:
            continue
        rows.append(f"{_ts(t)} {seg['title']}")
        last = t
    return "\n".join(rows) if len(rows) >= 3 else ""


TITLE_MAX = 50          # parents browse on phones: longer titles are cut off in the feed
_AUDIENCE = re.compile(r"\s+for (toddlers|kids|preschoolers|children|babies)\s*$", re.I)
_DANGLING = {"a", "an", "and", "the", "of", "for", "with", "to", "in", "on", "&", "|", "-", "–", ":"}


def fit_title(title: str, limit: int = TITLE_MAX) -> str:
    """Shorten a title to `limit` without ever ending mid-phrase: drop a '| tail', then a trailing 'for Toddlers',
    then whole words (never leaving 'and', 'for', '&' dangling)."""
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    while len(t) > limit and re.search(r"\s[|–:-]\s", t):
        t = re.split(r"\s[|–:-]\s(?!.*\s[|–:-]\s)", t)[0].strip()          # drop the last '| part'
    if len(t) > limit:
        t = _AUDIENCE.sub("", t).strip()
    if len(t) > limit:                    # a natural stop: after 'Bigger?', 'Fossils!' or an emoji
        stops = [m.end() for m in re.finditer(r"[!?](?=\s)|[^\w\s&|:,.'\-–]+(?=\s)", t) if 25 <= m.end() <= limit]
        if stops:
            return t[:max(stops)].strip()
    if len(t) > limit:
        words = t.split()
        while words and len(" ".join(words)) > limit:
            words.pop()
        while words and words[-1].lower() in _DANGLING:
            words.pop()
        t = " ".join(words)
    return t


def build(script: dict, settings: dict, timeline: list[dict] | None = None) -> dict:
    cat = categories.get(script["category"])
    b = psychology.band(script["age_band"])
    name = settings.get("channel_name", "Hoppy Hop Hop")
    style = (settings.get("_variant") or {}).get("title", "search")
    phrase, series = SEARCH.get(script["category"], (f"{cat['name'].split('&')[0].strip()} for Kids", ""))
    # the most exciting part first (what the child will SEE), then the search phrase; never the channel name
    style_rule = {
        "search": f"START with the story's exciting subject in 2-6 words ('The Clever Fox & the Rooster 🦊'), then the "
                  f"search phrase ('{phrase}')",
        "character": "START with the exciting moment our character has ('Bo's Giant Feast! 🍉'), then the search phrase "
                     f"('{phrase}')",
        "question": "START with a curious question a child would ask ('Why Is the Sky Blue?'), then the search phrase",
    }.get(style, f"START with the story's exciting subject, then '{phrase}'")
    src = script.get("source")
    fallback = {
        "title": fit_title(f"{script.get('title_idea') or script['topic']} {cat['emoji']} {phrase}"),
        "hook": script.get("summary", ""),
        "tags": [cat["name"], "kids songs", "learning for kids", "preschool", "toddler learning",
                 "nursery rhymes", "educational videos for kids", name] + script.get("key_words", []),
    }
    try:
        data, _ = complete_json(
            "You write YouTube metadata for a trusted kids channel. Parents read it. Honest, warm, specific, no "
            "clickbait lies, no ALL CAPS, at most 2 emojis. Never put the channel name in the title. Titles lead with the exact phrases parents search "
            "(e.g. 'Counting Song', 'Learn Colors', 'Bedtime Story', 'Nursery Rhymes', 'for Toddlers'), but ONLY phrases "
            "that truly describe THIS episode: never name a skill (colors, counting, ABC...) the episode doesn't teach. "
            "JSON only.",
            f"Channel: {name}. Episode: {script.get('title_idea')} ({cat['name']}, ages {b['ages']}). "
            f"Summary: {script.get('summary')}. Key words: {script.get('key_words')}. Lesson: {script.get('lesson')}.\n"
            f"Return {{\"title\": str (max {TITLE_MAX} chars, short and clear beats keyword-packed; {style_rule}, e.g. one of: "
            f"{', '.join(SEO_KEYWORDS[:14])}; then what the child learns + who it's for, e.g. 'Counting Song "
            "🍎 Count to 10 with Pip'), \"hook\": str (ONE plain sentence: what happens and what the child learns), "
            "\"learning_goals\": [3 short bullets], \"thumb_text\": str (2-3 BIG words a toddler's parent gets at a glance on a "
            "phone, e.g. 'Count to 10!', 'Sleepy Fox'), "
            "\"tags\": [12-15 search phrases parents type]}",
            temperature=0.6, max_tokens=900)
        meta = {**fallback, **{k: v for k, v in data.items() if v}}
    except (LLMError, ValueError):
        meta = dict(fallback)
    meta["title"] = re.sub(r"\s+", " ", str(meta["title"])).strip()
    meta["title"] = fit_title(re.sub(rf"\s*[|\-–]\s*{re.escape(name)}\s*$", "", meta["title"], flags=re.I))  # no brand
    if any(i["level"] == "block" for i in safety.check_title(meta["title"])) or unfounded(meta["title"], script):
        meta["title"] = fallback["title"]
    if unfounded(meta.get("thumb_text", ""), script):
        meta["thumb_text"] = ""
    meta["learning_goals"] = [g for g in meta.get("learning_goals") or [] if not unfounded(g, script)]
    meta["tags"] = [t for t in meta.get("tags", []) if not unfounded(t, script)]
    goals = meta.get("learning_goals") or []
    if src:
        from .books import credit
        parts_src = [credit(src), ""]
    else:
        parts_src = []
    cast_line = "Meet the friends: Hoppy 🐸 Sunny ☀️ Pip 🐧 Mimi 🐰 Bo 🦕 Zuzu 🦊 and Nana Owl 🦉"
    handle = (settings.get("channel_handle") or "").strip()
    sub_link = f" 👉 youtube.com/{handle}?sub_confirmation=1" if handle.startswith("@") else ""
    parts = [meta.get("hook", ""), ""]
    ch = chapters(timeline or [])
    if ch:                                    # parents jump to the song: timestamps right under the summary
        parts += [ch, ""]
    if settings.get("growth_cta", True):
        parts += [f"👉 Grown-ups: subscribe to {name} for new episodes every day — songs, stories and learning "
                  f"your child will ask for again and again!{sub_link}", ""]
    if goals:
        parts += ["In this episode your child will:"] + [f"• {g}" for g in goals] + [""]
    parts += parts_src + [cast_line, "",
              f"{name} makes calm, kind, curious videos for children {b['ages']}: songs, stories, counting, letters, "
              "feelings and the whole wide world. Made with child-development principles: gentle pace, real pauses "
              "for your child to answer, movement breaks and a calm goodbye.",
              "", "For grown-ups: watch together when you can and ask your child what they learned!",
              "", hashtags.line(script["category"], script)]
    meta["description"] = "\n".join(parts)[:4900]
    meta["tags"] = hashtags.clean_tags(meta.get("tags", []), name)[:20]      # never cut mid-word, no brand typos
    meta["category_id"] = cat["yt"]
    meta["playlist"] = series or f"{cat['emoji']} {cat['name']} | {name}"
    return meta


def localize(meta: dict, langs: list[str]) -> dict:
    """{lang: {title, description}} — one model call; failures just mean fewer translations."""
    langs = [lg for lg in langs if lg in languages.LANGS and lg != "en"]
    if not langs:
        return {}
    try:
        data, _ = complete_json(
            "You are a professional children's-media translator. Natural, warm, simple words parents use. "
            "Keep emojis and the chapter timestamps exactly. JSON only.",
            f"Translate this YouTube title and description into: {', '.join(langs)}.\n"
            f"TITLE: {meta['title']}\nDESCRIPTION:\n{meta['description'][:2500]}\n\n"
            "Return {\"<lang code>\": {\"title\": str (max 100 chars), \"description\": str}}",
            temperature=0.3, max_tokens=8000)
    except (LLMError, ValueError):
        return {}
    out = {}
    for lg in langs:
        v = data.get(lg) if isinstance(data, dict) else None
        if isinstance(v, dict) and v.get("title"):
            out[lg] = {"title": str(v["title"])[:100], "description": str(v.get("description", ""))[:4900]}
    return out


def translate_script(script: dict, lang: str) -> dict:
    """A dubbed edition: same scenes/cards/timing structure, text in `lang`. Song lines stay short and rhythmic."""
    import copy
    out = copy.deepcopy(script)
    out["language"] = lang
    for seg in out["segments"]:
        lines = [sc["text"] for sc in seg["scenes"]]
        cards = [(i, sc["card"]) for i, sc in enumerate(seg["scenes"]) if sc.get("card")]
        data, _ = complete_json(
            "You translate children's TV scripts for dubbing. Keep it simple, warm and natural for a "
            f"{psychology.band(script['age_band'])['ages']}-year-old native speaker; songs must rhyme and keep "
            "short lines. Keep the same number of lines. JSON only.",
            f"Language: {languages.name(lang)}.\nSegment kind: {seg['kind']}. Segment title: {seg['title']}\nLINES: {lines}\n"
            f"CARD TEXTS: {[{**c, 'i': i} for i, c in cards]}\n"
            "Return {\"title\": str, \"lines\": [same count], \"cards\": [{\"i\": int, \"text\": str, \"word\": str}]}",
            temperature=0.3, max_tokens=4000)
        new = data.get("lines") or []
        if len(new) != len(lines):
            raise ValueError(f"translation of '{seg['title']}' returned {len(new)} lines, expected {len(lines)}")
        seg["title"] = str(data.get("title") or seg["title"])[:40]
        for sc, t in zip(seg["scenes"], new):
            sc["text"] = str(t)
        for c in data.get("cards") or []:
            try:
                card = seg["scenes"][int(c["i"])]["card"]
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            if card:
                for k in ("text", "word"):
                    if c.get(k) and k in card:
                        card[k] = str(c[k])
    return out
