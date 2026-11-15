"""YouTube metadata: honest, parent-friendly titles, chapters from the real timeline, translations.

Parents search and pick for the under-8s, so titles say plainly what the child gets ("Learn to Count to 10 |
Songs & Games for Toddlers"), never clickbait. Chapters let parents jump to the song their child loves.
"""
from __future__ import annotations

import re

from ..llm.router import LLMError, complete_json
from . import categories, languages, psychology, safety
from .growth import SEO_KEYWORDS


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


def build(script: dict, settings: dict, timeline: list[dict] | None = None) -> dict:
    cat = categories.get(script["category"])
    b = psychology.band(script["age_band"])
    name = settings.get("channel_name", "Hoppy Hop Hop")
    style = (settings.get("_variant") or {}).get("title", "search")
    style_rule = {
        "search": "START with a high-search phrase parents type",
        "character": "START with our character doing something ('Pip Learns to Count!'), then the search phrase",
        "question": "START with a curious question a child would ask ('Why Is the Sky Blue?'), then the search phrase",
    }.get(style, "START with a high-search phrase parents type")
    src = script.get("source")
    fallback = {
        "title": f"{script.get('title_idea') or script['topic']} | {cat['name']} for Kids {b['ages']} | {name}"[:100],
        "hook": script.get("summary", ""),
        "tags": [cat["name"], "kids songs", "learning for kids", "preschool", "toddler learning",
                 "nursery rhymes", "educational videos for kids", name] + script.get("key_words", []),
    }
    try:
        data, _ = complete_json(
            "You write YouTube metadata for a trusted kids channel. Parents read it. Honest, warm, specific, no "
            "clickbait lies, no ALL CAPS, at most 2 emojis. Titles lead with the exact phrases parents search "
            "(e.g. 'Counting Song', 'Learn Colors', 'Bedtime Story', 'Nursery Rhymes', 'for Toddlers'). JSON only.",
            f"Channel: {name}. Episode: {script.get('title_idea')} ({cat['name']}, ages {b['ages']}). "
            f"Summary: {script.get('summary')}. Key words: {script.get('key_words')}. Lesson: {script.get('lesson')}.\n"
            f"Return {{\"title\": str (max 70 chars; {style_rule}, e.g. one of: "
            f"{', '.join(SEO_KEYWORDS[:14])}; then what the child learns + who it's for, e.g. 'Counting Song "
            "🍎 Count to 10 with Pip | Learning for Toddlers'), \"hook\": str (2 warm sentences for parents), "
            "\"learning_goals\": [3 short bullets], \"thumb_text\": str (1-3 BIG words for the thumbnail, e.g. 'Count to 10!'), "
            "\"tags\": [12-15 search phrases parents type]}",
            temperature=0.6, max_tokens=900)
        meta = {**fallback, **{k: v for k, v in data.items() if v}}
    except (LLMError, ValueError):
        meta = dict(fallback)
    meta["title"] = re.sub(r"\s+", " ", str(meta["title"])).strip()[:100]
    if any(i["level"] == "block" for i in safety.check_title(meta["title"])):
        meta["title"] = fallback["title"]
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
    if settings.get("growth_cta", True):
        parts += [f"👉 Grown-ups: subscribe to {name} for new episodes every day — songs, stories and learning "
                  f"your child will ask for again and again!{sub_link}", ""]
    if goals:
        parts += ["In this episode your child will:"] + [f"• {g}" for g in goals] + [""]
    ch = chapters(timeline or [])
    if ch:
        parts += ["Chapters:", ch, ""]
    parts += parts_src + [cast_line, "",
              f"{name} makes calm, kind, curious videos for children {b['ages']}: songs, stories, counting, letters, "
              "feelings and the whole wide world. Made with child-development principles: gentle pace, real pauses "
              "for your child to answer, movement breaks and a calm goodbye.",
              "", "For grown-ups: watch together when you can and ask your child what they learned!",
              "", (f"#{handle[1:]} " if handle.startswith("@") else "") + "#kidslearning #preschool #" + re.sub(r"[^A-Za-z0-9]", "", cat["name"].split("&")[0]).lower()]
    meta["description"] = "\n".join(parts)[:4900]
    meta["tags"] = list(dict.fromkeys(str(t)[:30] for t in meta.get("tags", [])))[:15]
    meta["category_id"] = cat["yt"]
    meta["playlist"] = f"{cat['emoji']} {cat['name']} | {name}"
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
