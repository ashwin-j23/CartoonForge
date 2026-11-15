"""Writer: a 10-15 minute episode in two passes.

1. Outline — the segment plan (blueprint from the category, minutes per segment, wonder question, key words).
2. Segments — each segment written on its own (long-form doesn't fit one model reply reliably), with the
   previous segment's last lines for continuity and the psychology brief every time.

With no AI key, `template_script` builds a complete, valid episode from templates so the whole pipeline
(voices, render, review) can be tried end to end.
"""
from __future__ import annotations

import random
import re

from ..llm.router import complete_json
from . import cast, categories, psychology

CARD_SPEC = """On-screen card (optional, only when it helps a child SEE the idea, shown exactly while the line is spoken):
  {"type":"count","object":"apple","n":3}           objects pop in one by one as the numbers are said
  {"type":"number","n":7}                           a big friendly numeral
  {"type":"letter","letter":"B","word":"Ball","object":"ball"}
  {"type":"word","text":"Kind","object":"heart"}     one key word (with a picture)
  {"type":"color","color":"red"}                    red|orange|yellow|green|blue|purple|pink|brown|black|white
  {"type":"shape","shape":"triangle","color":"blue"} circle|square|triangle|rectangle|star|heart|oval|diamond
  {"type":"fact","text":"Elephants drink with their trunks","object":"elephant"}   max 8 words
  {"type":"question","text":"How many apples?"}
  {"type":"page","text":"a short line quoted from the book (max 14 words)","object":"lion"}   (storybook episodes)
Objects you may use: """

SCENE_SPEC = """Each scene is ONE spoken line:
{"speaker": one of %s,
 "text": "what they say (1-2 short sentences)",
 "kind": "line" | "question" (asks the viewer, a pause follows) | "answer" (celebrates the answer) | "sing" (a song line),
 "emotion": "happy"|"excited"|"surprised"|"thinking"|"sad"|"worried"|"proud"|"sleepy"|"calm",
 "action": "idle"|"wave"|"jump"|"dance"|"point"|"think"|"clap"|"sleep"|"walk"|"stretch",
 "cast": ["2-3 character ids on screen"],
 "roles": {} or {"bo": "the Lion", "pip": "the Mouse"} when our friends ACT a story's characters (shown as name tags),
 "card": null or a card}"""


def _objects() -> list[str]:
    from ..render.icons import ICONS
    return sorted(ICONS)


def _source_block(source: dict | None) -> str:
    if not source:
        return ""
    words = source.get("text", "").split()
    return (f"\nADAPT THIS PUBLIC-DOMAIN STORY: \"{source.get('title')}\" from {source.get('book')} by "
            f"{', '.join(source.get('authors') or [])}. Keep its plot, characters and lesson, retell it simply for this "
            "age, soften anything frightening or violent (nobody is hurt or eaten; problems are solved kindly). If the book "
            "was written for grown-ups (an epic, a novel, a play), keep only the child-sized heart of this part — the "
            "adventure, the friendship, the clever idea, the wonder — leave out romance, war, cruelty and death, explain "
            "old-fashioned words, and keep it true to the book's spirit. Have "
            "the STORY'S OWN characters appear and speak (design them in \"characters\"); Nana Owl narrates and our friends "
            "react, ask questions and help the child think. Story segments follow the story in order across the episode; "
            "other segments (song, game, feelings, recap) are about this story.\n"
            f"STORY TEXT:\n{' '.join(words[:3500])}{' …' if len(words) > 3500 else ''}\n")


def outline(category: dict, topic: str, band_id: str, minutes: float, lang: str = "en", source: dict | None = None,
            hints: str = "") -> dict:
    b = psychology.band(band_id)
    bp = category["blueprint"]
    system = ("You are the head writer of a warm, award-quality preschool/kids TV show on YouTube. You design "
              "episodes with child-development experts. Reply with JSON only.")
    user = (f"Plan one {minutes:.0f}-minute episode.\nCategory: {category['name']}\nTopic: {topic}\n"
            f"{psychology.writer_brief(band_id)}\nCAST:\n{cast.bible()}\n{_library_bible()}\n"
            f"Lead character for this category: {category['lead']}.\n"
            f"Segment order (keep it): {bp}\nSegment kinds: {categories.SEGMENT_KINDS}\n"
            f"Sets you can use: {', '.join(sorted(_sets()))}. Suggested: {category['sets']}.\n"
            f"Language of the episode: {lang}.\n{_source_block(source)}"
            f"{('WHAT OUR AUDIENCE DATA SAYS: ' + hints) if hints else ''}\n\n"
            "Return JSON: {\"title_idea\": str, \"summary\": str (2 sentences for parents: what the child learns), "
            "\"key_words\": [3-6 words the child should learn, single words], \"lesson\": str, "
            "\"characters\": [0-6 characters this episode needs besides our cast (a recurring friend: just {\"id\": its id}; "
            "otherwise a NEW design (story characters for books/fables, "
            "an animal Zuzu meets, a king, a girl from Nairobi...). Each: {\"id\": short lowercase id, \"name\": str, "
            "\"kind\": \"animal\"|\"human\", \"species\": str (animals: fox, wolf, lion, bear, rabbit, mouse, crow, tortoise, "
            "hare, elephant, monkey, crocodile, frog, owl, dragon, ant, grasshopper, horse, goat, sheep, pig, cow, cat, dog, "
            "tiger, deer, fish, whale...), \"gender\": \"f\"|\"m\", \"age\": \"child\"|\"adult\"|\"old\", "
            "\"colors\": {\"main\": \"#rrggbb\", \"accent\": \"#rrggbb\"}, \"outfit\": none|crown|cape|dress|robe|scarf|bow|"
            "glasses|wizard_hat|cap|straw_hat|chef_hat|turban|helmet|feathers, humans also \"skin\": deep|brown|tan|olive|light|pale, "
            "\"hair\": short|long|curly|bun|braids|afro|ponytail|spiky|bald, \"hair_color\": black|brown|blonde|red|grey|white, "
            "\"personality\": str}. Show the world's diversity in human characters.], "
            "\"segments\": [{\"kind\": str, \"title\": str (2-4 words, shown as a chapter), \"set\": str, "
            "\"minutes\": number, \"wonder\": str (the question that opens it), \"beats\": [3-6 short story/teaching beats], "
            "\"song_idea\": str (only for song)}]}\n"
            f"Minutes must add up to about {minutes:.0f}. hello ≈ 0.6, goodbye ≈ 0.6, recap ≈ 1, songs ≈ 1.2-1.6, "
            f"others share the rest (each 1.5-{b['segment'] + 0.6:.1f}).")
    data, _ = complete_json(system, user + "\nReturn compact (minified) JSON.", temperature=0.8, max_tokens=6000,
                            salvage=False)
    if isinstance(data, list):                         # some models answer with the bare list
        data = {"segments": data}
    if not isinstance(data, dict):
        raise ValueError("outline was not a JSON object")
    segs = [s for s in data.get("segments") or [] if isinstance(s, dict)]
    data["segments"] = segs
    if len(segs) < 5:
        raise ValueError("outline too short")
    for s in segs:
        s["kind"] = s.get("kind") if s.get("kind") in categories.SEGMENT_KINDS else "learn"
        s["set"] = s.get("set") if s.get("set") in _sets() else category["sets"][0]
    return data


def write_segment(seg: dict, plan: dict, category: dict, band_id: str, prev_tail: list[str], lang: str = "en",
                  fix_notes: str = "", source: dict | None = None) -> list[dict]:
    b = psychology.band(band_id)
    words = int(float(seg.get("minutes") or 1.5) * b["wpm"])
    system = ("You write the spoken script for a gentle, funny, educational kids show. Every line is spoken aloud "
              "by a character to a child watching. Reply with JSON only.")
    kind = seg["kind"]
    extra = {
        "hello": "THE HOOK (first 10 seconds decide if a child stays): open with the most exciting moment of today "
                 "as a quick tease ('Today… a dinosaur egg is going to hatch!'), THEN Sunny's catchphrase "
                 f"\"{cast.CAST['sunny']['catchphrase']}\", greet every friend by name, friends wave, say what we'll do. "
                 "Short, energetic lines.",
        "goodbye": "Recap one thing we learned, praise the child's effort (listening, counting, singing), a calm "
                   "goodbye from every friend, a tiny 'next time we will…' preview that makes them want to come back, "
                   "'See you next time, little sprouts!'. Calm, slower.",
        "song": "Write the SONG: 10-16 lines, kind=\"sing\", speaker mimi (others may join). Lines of 4-8 words, "
                "strong simple rhythm and rhyme (AABB), a 2-line CHORUS that repeats at least 3 times, uses the key "
                "words. Before the song one line invites the child to sing along; after it one line praises them.",
        "movement": "Ask the child to stand up. 6-10 actions acting out the topic (hop like a frog, reach up high), "
                    "count the moves together, action field matches (jump/stretch/dance/clap), then calm down "
                    "with one deep breath.",
        "game": "3-5 rounds: a 'question' line with a card, then an 'answer' line celebrating ('Yes! ...').",
        "calm": "Slow breathing together: 'Breathe in… and out…' 3 times, soft and quiet, emotion calm.",
        "feelings": "A character has a big feeling about something small. Name the feeling, show it is okay, calm "
                    "down together (deep breath), then solve it kindly. Ask the child how they would feel.",
        "story": "Tell it like a picture book: a simple problem, three tries, a kind solution, feelings named. "
                 "Nana Owl narrates; characters speak their own lines. For fables keep the traditional lesson.",
        "explore": "Zuzu takes everyone somewhere new. Discover 3 things, each with a fact card and a question.",
        "recap": "Quick recap: show the cards again, ask the child to say each key word.",
        "learn": "Teach one idea step by step with cards on screen exactly when the words are said; Pip makes one "
                 "small mistake that the child helps fix.",
    }.get(kind, "")
    user = (f"EPISODE: {plan.get('title_idea')} — {category['name']}. Key words: {plan.get('key_words')}. "
            f"Lesson: {plan.get('lesson', '')}\n{psychology.writer_brief(band_id)}\nCAST:\n{cast.bible()}\n"
            f"{_guest_bible(plan.get('characters'))}\n"
            f"Write SEGMENT \"{seg.get('title')}\" (kind: {kind}). Opening wonder question: {seg.get('wonder', '')}\n"
            f"Beats: {seg.get('beats', [])}\n{('Song idea: ' + seg['song_idea']) if seg.get('song_idea') else ''}\n"
            f"{extra}\nLength: about {words} spoken words ({seg.get('minutes')} min). Language: {lang}.\n"
            f"The previous segment ended with: {prev_tail[-3:] if prev_tail else '(start of episode)'}\n"
            f"{('FIX THESE PROBLEMS from the reviewer: ' + fix_notes) if fix_notes else ''}\n"
            f"{_source_block(source) if source and kind == 'story' else ''}"
            "Keep lines short and lively: many short lines beat a few long ones (each line is its own shot).\n\n"
            f"{SCENE_SPEC % (cast.SPEAKERS + [g['id'] for g in plan.get('characters') or []])}\n{CARD_SPEC}{', '.join(_objects())}\n\n"
            "Return JSON: {\"scenes\": [ ... ]}")
    data, _ = complete_json(system, user + "\nReturn compact (minified) JSON.", temperature=0.85, max_tokens=6000)
    scenes = data if isinstance(data, list) else (data.get("scenes") or [] if isinstance(data, dict) else [])
    return clean_scenes(scenes, seg, category, {g["id"] for g in plan.get("characters") or []})


def clean_scenes(scenes: list, seg: dict, category: dict, guests: set | None = None) -> list[dict]:
    guests = guests or set()
    ok = lambda c: c in cast.CAST or c in guests   # noqa: E731
    out = []
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        text = re.sub(r"\s+", " ", str(sc.get("text") or "")).strip()
        if not text:
            continue
        spk = sc.get("speaker") if ok(sc.get("speaker")) else ("mimi" if seg["kind"] == "song" else category["lead"])
        on = [c for c in (sc.get("cast") or []) if ok(c) and c != "sunny"][:3]
        if spk != "sunny" and spk not in on:
            on = ([spk] + on)[:3]
        if cast.STAR not in on and len(on) < 3 and seg["kind"] not in ("calm",):
            on = on + [cast.STAR]                                    # the star is always in the picture
        kind = sc.get("kind") if sc.get("kind") in ("line", "question", "answer", "sing") else "line"
        if seg["kind"] == "song" and kind == "line" and len(text.split()) <= 9 and not text.endswith("?"):
            kind = "sing"
        roles = {k: str(v)[:22] for k, v in (sc.get("roles") or {}).items() if k in cast.CAST} \
            if isinstance(sc.get("roles"), dict) else {}
        out.append({"speaker": spk, "text": text[:400], "kind": kind,
                    "emotion": sc.get("emotion") or "happy", "action": sc.get("action") or "idle",
                    "cast": on or [category["lead"]], "card": _card(sc.get("card")), **({"roles": roles} if roles else {})})
    return out


def clean_characters(chars) -> list[dict]:
    """Story characters from the outline: unique safe ids, never clashing with the main cast, max 6."""
    out, seen = [], set(cast.CAST)
    for g in chars or []:
        if not isinstance(g, dict) or not (g.get("name") or g.get("species")):
            continue
        cid = re.sub(r"[^a-z0-9_]", "", str(g.get("id") or g.get("name") or "guest").lower().replace(" ", "_"))[:20] or "guest"
        while cid in seen:
            cid += "2"
        seen.add(cid)
        keep = {k: g[k] for k in ("name", "kind", "species", "gender", "age", "colors", "outfit", "skin", "hair",
                                  "hair_color", "personality", "look", "catchphrase") if g.get(k) is not None}
        keep["name"] = str(keep.get("name") or keep.get("species", "Friend")).strip()[:30]
        out.append({"id": cid, **keep})
        if len(out) >= 6:
            break
    return out


def _library_bible() -> str:
    try:
        from . import library
        return library.bible()
    except Exception:  # noqa: BLE001
        return ""


def _from_library(chars: list[dict]) -> list[dict]:
    """Outline characters that already exist in the library keep their saved design (same look, same voice)."""
    try:
        from . import library
    except Exception:  # noqa: BLE001
        return chars
    out = []
    for g in chars:
        hit = library.match(g)
        out.append({**library.spec(hit), "id": hit["id"]} if hit else g)
    seen, uniq = set(), []
    for g in out:
        if g["id"] not in seen:
            seen.add(g["id"])
            uniq.append(g)
    return uniq


def _guest_bible(chars) -> str:
    if not chars:
        return ""
    return "STORY CHARACTERS (they can speak; use their id as speaker and in cast):\n" + "\n".join(
        f"- {g['id']}: {g['name']} ({g.get('species') or g.get('kind', '')}, {g.get('age', 'adult')}). "
        f"{g.get('personality', '')}" for g in chars)


def _card(c) -> dict | None:
    if not isinstance(c, dict) or c.get("type") not in ("count", "number", "letter", "word", "color", "shape", "fact", "question", "page"):
        return None
    c = {k: v for k, v in c.items() if isinstance(v, (str, int, float))}
    if c["type"] in ("count", "number"):
        try:
            c["n"] = max(0, min(20, int(c.get("n", 1))))
        except (TypeError, ValueError):
            c["n"] = 3
    return c


def write_episode(category_id: str, topic: str, band_id: str, minutes: float, lang: str = "en",
                  log=print, source: dict | None = None, hints: str = "") -> dict:
    cat = categories.get(category_id)
    plan = outline(cat, topic, band_id, minutes, lang, source, hints)
    raw = [g if g.get("name") or g.get("species") else {**g, "name": g.get("id", "")} for g in plan.get("characters") or []
           if isinstance(g, dict)]
    plan["characters"] = _from_library(clean_characters(raw))
    segments, tail = [], []
    for seg in plan["segments"]:
        scenes = write_segment(seg, plan, cat, band_id, tail, lang, source=source)
        if not scenes:
            raise ValueError(f"empty segment {seg.get('title')}")
        segments.append({"kind": seg["kind"], "title": seg.get("title") or seg["kind"].title(), "set": seg["set"],
                         "scenes": scenes})
        tail = [s["text"] for s in scenes]
        log(f"Wrote segment '{seg.get('title')}' ({len(scenes)} lines)")
    return {"title_idea": plan.get("title_idea") or topic, "summary": plan.get("summary", ""),
            "key_words": [str(k) for k in plan.get("key_words", [])][:6], "lesson": plan.get("lesson", ""),
            "topic": topic, "category": cat["id"], "age_band": band_id, "language": lang, "segments": segments,
            "outline": plan["segments"], "writer": "ai", "characters": plan["characters"],
            **({"source": {k: v for k, v in source.items() if k != "text"}} if source else {})}


def rewrite_segments(script: dict, notes: dict[int, str], log=print) -> dict:
    """Rewrite only the segments the Critic flagged (index -> notes)."""
    cat = categories.get(script["category"])
    plan = {"title_idea": script.get("title_idea"), "key_words": script.get("key_words"), "lesson": script.get("lesson"),
            "characters": script.get("characters") or []}
    outl = script.get("outline") or []
    for i, note in notes.items():
        if i >= len(script["segments"]):
            continue
        seg = {**(outl[i] if i < len(outl) else {}), **{k: script["segments"][i][k] for k in ("kind", "title", "set")}}
        seg.setdefault("minutes", 1.5)
        tail = [s["text"] for s in script["segments"][i - 1]["scenes"]] if i else []
        scenes = write_segment(seg, plan, cat, script["age_band"], tail, script.get("language", "en"), fix_notes=note)
        if scenes:
            script["segments"][i]["scenes"] = scenes
            log(f"Rewrote segment {i + 1} '{seg['title']}'")
    return script


def _sets() -> set[str]:
    from ..render.sets import SETS
    return set(SETS)


# ---------------------------------------------------------------- offline template writer
NUM_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
TEMPLATE_OBJECTS = ["apple", "star", "duck", "balloon", "fish", "flower", "ball", "butterfly", "strawberry", "car",
                    "cupcake", "bee", "kite", "boat", "shell"]


def _plural(o: str) -> str:
    if o in ("fish", "sheep"):
        return o
    return o[:-1] + "ies" if o.endswith("y") and o[-2:-1] not in "aeiou" else (o + "es" if o.endswith(("sh", "ch", "s")) else o + "s")


def _num(n: int, cap: bool = True) -> str:
    w = NUM_WORDS[n] if 0 <= n < len(NUM_WORDS) else str(n)
    return w.capitalize() if cap else w


TTS_WPM = 190          # what the neural voices (Kokoro) really speak at, measured on a full render
TTS_MIN_LINE = .86     # a one-word line ("Three!") still takes this long


def template_seconds(segs: list[dict], band_id: str) -> float:
    """Episode length the way the real soundtrack times it (render/audio.py), calibrated on a full Kokoro render
    (model 527.5 s vs real 528.7 s): spoken lines at the voices' real speed + ~0.47 s breath, answer pauses at the
    band's length, sung lines on the beat grid, 0.9 s segment gaps, the theme jingle and the end card.
    (episode.estimate_audio assumes the band's slower target wpm, so its preview runs ~30% long for these voices.)"""
    b = psychology.band(band_id)
    t = 3.5 + 6.3
    for i, seg in enumerate(segs):
        t += .9 if i else 0
        for sc in seg["scenes"]:
            n = len(sc["text"].split())
            if sc.get("kind") == "sing" and seg["kind"] == "song":
                t += max(1.0, n / b["wpm"] * 60) + .4
            else:
                t += max(TTS_MIN_LINE, n / TTS_WPM * 60) + (b["pause"] if sc.get("kind") == "question" else .47)
    return t


def template_script(category_id: str, topic: str, band_id: str, minutes: float = 12, seed: int = 0) -> dict:
    """A complete, psychology-compliant counting episode without any AI (demo + tests), as long as asked (±10%).

    Hoppy is the star. Built from varied blocks — counting rounds (different objects, counters and helpers), two song
    verses, movement breaks, a feelings moment, a story starring Hoppy, number games — added until the target length
    is reached, then a recap and the goodbye ritual. Every question gets an answer; effort is praised, not ability."""
    import zlib
    rnd = random.Random(seed or zlib.crc32(topic.encode()) & 0xFFFF)
    cat = categories.get(category_id)
    objs = rnd.sample(TEMPLATE_OBJECTS, len(TEMPLATE_OBJECTS))
    sets_ = cat["sets"]
    target = max(2.0, float(minutes or 12)) * 60

    def S(spk, text, kind="line", emo="happy", act="idle", on=None, card=None):
        cast_ = list(on or ["hoppy", "pip"])
        if "hoppy" not in cast_:                                      # the star is in every scene
            cast_ = ["hoppy"] + cast_[:2]
        if spk != "sunny" and spk not in cast_:                       # whoever talks is on screen
            cast_ = cast_ + [spk] if len(cast_) < 3 else [c for c in cast_ if c != cast_[-1] or c == "hoppy"][:2] + [spk]
        return {"speaker": spk, "text": text, "kind": kind, "emotion": emo, "action": act, "cast": cast_, "card": card}

    # ---- blocks -------------------------------------------------------------------------------------------------
    counters = ["mimi", "pip", "zuzu", "hoppy"]
    helpers = ["bo", "pip", "zuzu", "mimi"]
    rounds = [0]

    def counting_round():
        r = rounds[0]
        rounds[0] += 1
        o = objs[r % len(objs)]
        os_ = _plural(o)
        n = [3, 5, 4, 6, 7, 5, 8, 6, 9, 10][r % 10]
        who, helper = counters[r % len(counters)], helpers[r % len(helpers)]
        trio = ["hoppy", who if who != "hoppy" else "pip", helper if helper not in ("hoppy", who) else "mimi"]
        opener = [f"Ribbit! Look, {os_}! Can you help me? How many {os_} can you see?",
                  f"Hop, hop! I found some {os_}. Let's count them together. How many?",
                  f"Ooh, {os_}! I wonder how many there are. Can you count with me?"][r % 3]
        sc = [S("hoppy", opener, "question", "surprised", "point", trio, {"type": "question", "text": f"How many {os_}?"})]
        for k in range(1, n + 1):
            sc.append(S(who, f"{_num(k)}!", "line", "happy", "point", trio, {"type": "count", "object": o, "n": k}))
        sc += [S("sunny", f"Yes! {_num(n)} {os_}! Great counting! You kept going!", "answer", "proud", "clap", trio,
                 {"type": "number", "n": n}),
               S(helper, f"Hoppy, I counted {n - 1}. I feel a little worried. Can you help me count again?", "question",
                 "worried", "think", trio),
               S("hoppy", "It's okay! Mistakes help us learn. Let's take a deep breath and count together.", "line", "calm",
                 "idle", trio),
               S(helper, f"You helped me! The number is {n}. I feel proud!", "answer", "proud", "jump", trio,
                 {"type": "number", "n": n}),
               S("hoppy", f"{_num(n)} {os_}. Say the number with me. {_num(n)}!", "line", "excited", "jump", trio,
                 {"type": "number", "n": n})]
        return {"kind": "learn", "title": f"Count the {os_}", "set": sets_[r % len(sets_)], "scenes": sc}

    verses = [0]

    def song():
        v = verses[0]
        verses[0] += 1
        o = objs[0]
        cast3 = ["hoppy", "mimi", "bo"]
        sc = [S("mimi", "Let's sing it together! Sing with me!" if v == 0 else "Here comes verse two! Sing along!",
                act="dance", on=cast3)]
        lines = ([("mimi", "One, two, three, count with me!", 3), ("mimi", "Four and five, we jump and jive!", 5),
                  ("hoppy", "Six and seven, hop to heaven!", 7), ("bo", "Eight, nine, ten, let's count again!", 10)]
                 if v % 2 == 0 else
                 [("hoppy", "One little frog jumps up so high!", 1), ("mimi", "Two little bunnies wave goodbye!", 2),
                  ("bo", "Three, four, five, we clap our hands!", 5), ("hoppy", "Count to ten in Number Land!", 10)])
        for rep in range(2):
            for spk, text, n in lines:
                card = {"type": "count", "object": o, "n": n} if n <= 5 else {"type": "number", "n": n}
                sc.append(S(spk, text, "sing", act="dance" if rep == 0 else "jump", on=cast3, card=card))
        sc.append(S("sunny", "Wonderful singing! You did it!" if v == 0 else "Great singing! You kept the beat!",
                    "answer", "proud", "clap", cast3))
        return {"kind": "song", "title": "Counting Song" if v == 0 else "Counting Song, Verse Two", "set": "stage",
                "scenes": sc}

    moves = [0]

    def movement():
        m = moves[0]
        moves[0] += 1
        cast3 = ["hoppy", "pip", "zuzu"]
        if m % 2 == 0:
            sc = [S("sunny", "Time to wiggle! Can you stand up?", "question", act="stretch", on=cast3),
                  S("hoppy", "Yes! Stand up tall, and hop with Hoppy!", "answer", "excited", "jump", cast3)]
            for k in range(1, 6):
                sc.append(S("hoppy", f"Hop {_num(k, False)}!", act="jump", on=cast3, card={"type": "number", "n": k}))
            sc += [S("pip", "Now stretch up high, like a tall tree!", act="stretch", on=cast3),
                   S("sunny", "Five hops! The number five! Now one big, slow breath. In… and out. Well done!",
                     emo="calm", on=cast3)]
            return {"kind": "movement", "title": "Jump and Count", "set": "playground", "scenes": sc}
        sc = [S("zuzu", "Let's clap and count! Can you clap with me?", "question", "excited", "clap", cast3),
              S("hoppy", "Ready? Clap, clap, clap!", "answer", "excited", "clap", cast3)]
        for k in range(1, 6):
            sc.append(S("zuzu", f"Clap {_num(k, False)}!", act="clap", on=cast3, card={"type": "number", "n": k}))
        sc += [S("hoppy", "Now stomp your feet! One, two, three!", act="jump", on=cast3,
                 card={"type": "number", "n": 3}),
               S("pip", "Wiggle your fingers, wiggle your toes!", act="dance", on=cast3),
               S("sunny", "Great moving! Now sit down softly. Well done!", emo="calm", on=cast3)]
        return {"kind": "movement", "title": "Clap and Count", "set": "playground", "scenes": sc}

    def feelings():
        cast3 = ["hoppy", "bo", "mimi"]
        sc = [S("bo", "Oh no. I tried to stack my blocks, and they fell down.", emo="sad", act="idle", on=cast3),
              S("hoppy", "Oh, Bo. You look sad. How do you feel?", "question", "worried", "idle", cast3,
                {"type": "word", "text": "Sad", "object": "heart"}),
              S("bo", "I feel sad, and a little bit cross.", "answer", "sad", on=cast3,
                card={"type": "word", "text": "Sad", "object": "heart"}),
              S("mimi", "It's okay to feel sad. Everybody feels sad sometimes.", emo="calm", on=cast3),
              S("hoppy", "When I feel sad, I take a big breath. Can you breathe with us?", "question", "calm", on=cast3),
              S("sunny", "Breathe in, two, three. And out, two, three. Lovely.", emo="calm", on=cast3),
              S("bo", "I feel calm now. Can I try again?", emo="calm", on=cast3),
              S("hoppy", "Yes! Let's count the blocks together. One, two, three, four!", "line", "excited", "point", cast3,
                {"type": "count", "object": "block", "n": 4}),
              S("bo", "I did it! I kept trying, and now I feel happy and proud!", "answer", "proud", "jump", cast3,
                {"type": "word", "text": "Proud", "object": "star"}),
              S("sunny", "You kept trying, Bo. Great job! How do you feel today, friend?", "question", "proud", on=cast3),
              S("mimi", "Happy? Sleepy? Excited? All feelings are okay.", "answer", "happy", on=cast3)]
        return {"kind": "feelings", "title": "How Do You Feel?", "set": sets_[0], "scenes": sc}

    def story():
        cast3 = ["hoppy", "pip", "mimi"]
        o = objs[1]
        os_ = _plural(o)
        sc = [S("sunny", "Story time! This is the story of Hoppy and the Lily Pads.", emo="calm", on=cast3),
              S("hoppy", f"I want to cross the pond to find the {os_}. But it is so big!", emo="worried", on=cast3),
              S("pip", "Look, Hoppy! Lily pads! You can hop on them, one by one.", emo="excited", act="point", on=cast3),
              S("hoppy", "How many lily pads can you see? Let's count them!", "question", "thinking", "think", cast3,
                {"type": "count", "object": "leaf", "n": 5}),
              S("mimi", "One, two, three, four, five! Five lily pads!", "answer", "excited", "point", cast3,
                {"type": "count", "object": "leaf", "n": 5})]
        for k in range(1, 6):
            sc.append(S("hoppy", f"Hop {_num(k, False)}!" + (" Wobble, wobble!" if k == 3 else ""),
                        act="jump", emo="worried" if k == 3 else "excited", on=cast3, card={"type": "number", "n": k}))
        sc += [S("hoppy", "Oops! The lily pad wobbled. I feel a bit scared.", emo="worried", on=cast3),
               S("pip", "You can do it, Hoppy! Keep trying! We believe in you!", emo="excited", act="wave", on=cast3),
               S("hoppy", "I'm brave. I will try again. Hop!", emo="proud", act="jump", on=cast3),
               S("hoppy", f"I made it! Look, here are the {os_}! How many are there?", "question", "excited", "point",
                 cast3, {"type": "count", "object": o, "n": 3}),
               S("mimi", f"Three {os_}! Hooray for Hoppy!", "answer", "excited", "clap", cast3,
                 {"type": "number", "n": 3}),
               S("sunny", "Hoppy felt scared, but he kept trying. That is very brave!", emo="proud", on=cast3),
               S("hoppy", "Thank you for cheering for me, friend! The end!", emo="excited", act="wave", on=cast3)]
        return {"kind": "story", "title": "Hoppy and the Lily Pads", "set": "garden", "scenes": sc}

    games = [0]

    def game():
        gidx = games[0]
        games[0] += 1
        cast3 = ["hoppy", "pip", "zuzu"]
        if gidx % 2 == 0:
            n = [4, 6, 8, 2][(gidx // 2) % 4]
            sc = [S("zuzu", "Let's play Number Hunt! I'm thinking of a number.", "line", "excited", "idle", cast3),
                  S("zuzu", f"It comes after {_num(n - 1, False)}. What number is it?", "question", "thinking", "think",
                    cast3, {"type": "question", "text": f"After {n - 1}?"}),
                  S("hoppy", f"It's {_num(n, False)}! The number {n}!", "answer", "excited", "jump", cast3,
                    {"type": "number", "n": n}),
                  S("sunny", "Great thinking! Let's try one more number.", emo="proud", on=cast3),
                  S("pip", f"What number comes before {_num(n + 2, False)}?", "question", "thinking", "think", cast3,
                    {"type": "question", "text": f"Before {n + 2}?"}),
                  S("hoppy", f"{_num(n + 1)}! The number {n + 1}! Good try, everyone!", "answer", "excited", "clap", cast3,
                    {"type": "number", "n": n + 1})]
            return {"kind": "game", "title": "Number Hunt", "set": sets_[gidx % len(sets_)], "scenes": sc}
        a, b = objs[2 + gidx % 5], objs[3 + gidx % 5]
        sc = [S("pip", f"Let's play More or Less! Here are some {_plural(a)}.", "line", "excited", "point", cast3,
                {"type": "count", "object": a, "n": 2}),
              S("pip", f"And here are some {_plural(b)}.", "line", "happy", "point", cast3,
                {"type": "count", "object": b, "n": 4}),
              S("hoppy", f"Which has more, the {_plural(a)} or the {_plural(b)}?", "question", "thinking", "think", cast3,
                {"type": "question", "text": "Which has more?"}),
              S("zuzu", f"The {_plural(b)}! Four is more than two!", "answer", "excited", "jump", cast3,
                {"type": "number", "n": 4}),
              S("sunny", "Great thinking! You looked carefully.", emo="proud", on=cast3)]
        return {"kind": "game", "title": "More or Less", "set": sets_[(gidx + 1) % len(sets_)], "scenes": sc}

    # ---- assemble -----------------------------------------------------------------------------------------------
    hello = [S("sunny", "Hello, hello, little sprouts! It's a sunny day!", act="wave"),
             S("hoppy", "Hop to it, friends! I'm Hoppy!", act="jump", emo="excited", on=["hoppy", "pip", "mimi"]),
             S("pip", "Hi! I'm Pip!", act="wave", emo="excited", on=["hoppy", "pip", "mimi"]),
             S("mimi", "And I'm Mimi! Hello, friend!", act="wave", on=["hoppy", "pip", "mimi"]),
             S("bo", "And me, Bo! Oopsie-daisy, I almost forgot to wave!", act="wave", on=["hoppy", "bo", "pip"]),
             S("sunny", f"Today we are {topic.lower()}. Are you ready? Let's go!", "question", act="jump")]
    segs = [{"kind": "hello", "title": "Hello!", "set": sets_[0], "scenes": hello}]
    core = [counting_round, song, movement]                    # always: learn, sing, move
    extra = [feelings, counting_round, story, game, song, counting_round, movement, game, counting_round]
    extra += [counting_round, game, counting_round, movement] * 8          # long episodes: keep varying

    def closing() -> list[dict]:
        counted = [_plural(objs[i]) for i in range(max(1, rounds[0]))]
        recap = [S("sunny", "What did we count today? Say it with me!", "question", act="point")]
        recap += [S("mimi", f"{c.capitalize()}!", "answer" if i == 0 else "line", on=["hoppy", "mimi"],
                    card={"type": "word", "text": c.capitalize(), "object": objs[i]}) for i, c in enumerate(counted[:6])]
        recap.append(S("hoppy", "Hooray for Hoppy and you! We counted every number. We kept trying!", emo="excited",
                       act="jump"))
        goodbye = [S("sunny", "You listened, you counted, you sang. You kept trying, and I'm so proud of you!",
                     emo="proud"),
                   S("hoppy", "Thank you for helping me today! Hop to it, and see you soon!", act="jump", emo="excited",
                     on=["hoppy", "pip", "mimi"]),
                   S("pip", "Bye-bye, friend!", act="wave"), S("mimi", "See you soon, Hoppy! See you soon, friend!", act="wave"),
                   S("bo", "Bye! Don't forget to give someone a hug!", act="wave", on=["hoppy", "mimi", "bo"]),
                   S("sunny", "See you next time, little sprouts!", emo="calm", act="wave")]
        return [{"kind": "recap", "title": "What We Learned", "set": sets_[0], "scenes": recap},
                {"kind": "goodbye", "title": "Goodbye!", "set": sets_[0], "scenes": goodbye}]

    for make in core:
        segs.append(make())
    for make in extra:
        snap = (rounds[0], verses[0], moves[0], games[0])
        if template_seconds(segs + closing(), band_id) >= target * .97:
            break
        seg = make()
        if template_seconds(segs + [seg] + closing(), band_id) > target * 1.08:
            rounds[0], verses[0], moves[0], games[0] = snap        # too long: try the next (maybe shorter) block
            continue
        segs.append(seg)
    segs += closing()
    keys = ["count", "number", _plural(objs[0]), "hoppy"]
    return {"title_idea": topic, "summary": f"Children practise {topic.lower()} with Hoppy: songs, games, a story and "
                                            f"movement.",
            "key_words": keys, "lesson": "Mistakes help us learn", "topic": topic,
            "category": cat["id"], "age_band": band_id, "language": "en", "segments": segs, "writer": "template"}
