"""The child-psychology playbook.

Every rule here is used by code: the Writer gets it as instructions, the Critic measures the script against it,
and the renderer takes its pacing numbers. The aim is attention that is *earned* — children come back because
the show is warm, predictable, funny and makes them feel clever — never attention that is *extracted* with
over-stimulation, fear or fake cliffhangers. That is also what YouTube rewards: its quality principles for
kids' content promote enriching, age-appropriate videos and demote "low-quality" ones (sensational, overly
commercial, encouraging bad behaviour) in recommendations and YouTube Kids, and parents — who press play for
the under-8s — keep returning to channels they trust.
"""
from __future__ import annotations

import re
from collections import Counter

# ---------------------------------------------------------------- age bands
# wpm: target narration speed. sentence: max words per sentence. shot: minimum seconds between visual cuts
# (fast cutting taxes young children's executive function: Lillard & Peterson 2011). segment: minutes per
# activity before switching (attention span ~ 2-3 min per year of age). pause: seconds of silence after a
# question so the child can answer out loud (Blue's Clues research: Anderson et al. 2000).
AGE_BANDS: dict[str, dict] = {
    "toddler": {
        "label": "Toddlers (1-3)", "ages": "1-3", "wpm": 100, "sentence": 7, "shot": 4.5, "segment": 1.8,
        "pause": 3.0, "interact_per_min": 1.6, "repeat_key": 5, "fk_grade": 0.5,
        "voice": "Very simple words, lots of naming ('Look! A duck. Quack quack!'), sounds and animal noises.",
        "content": "Naming things, colours, animal sounds, body parts, routines (bath, food, sleep), lullabies.",
    },
    "preschool": {
        "label": "Preschool (3-5)", "ages": "3-5", "wpm": 115, "sentence": 10, "shot": 3.5, "segment": 2.2,
        "pause": 2.6, "interact_per_min": 1.2, "repeat_key": 4, "fk_grade": 1.5,
        "voice": "Short sentences, concrete words, one new idea at a time, playful sounds, rhymes.",
        "content": "Counting to 20, ABC & phonics, shapes, feelings, friendship, simple science, fables.",
    },
    "early": {
        "label": "Early school (5-8)", "ages": "5-8", "wpm": 130, "sentence": 14, "shot": 3.0, "segment": 2.8,
        "pause": 2.2, "interact_per_min": 0.8, "repeat_key": 3, "fk_grade": 2.8,
        "voice": "Clear explanations with one 'wow' fact per idea, jokes and wordplay, 'why' and 'how' questions.",
        "content": "Science, space, animals, world cultures, early maths, reading words, stories with a lesson.",
    },
    "big": {
        "label": "Big kids (8-12)", "ages": "8-12", "wpm": 145, "sentence": 18, "shot": 2.6, "segment": 3.2,
        "pause": 1.8, "interact_per_min": 0.5, "repeat_key": 2, "fk_grade": 4.5,
        "voice": "Smart and funny, never babyish. Challenge them: riddles, 'can you guess', surprising facts.",
        "content": "How things work, history adventures, geography, puzzles, nature mysteries, big questions.",
    },
}


# ---------------------------------------------------------------- pace profiles (Settings → pace)
# shot: (min, max) seconds between camera cuts. zoom: max close-up. motion: character energy. tempo: music speed.
PACES: dict[str, dict] = {
    "calm": {"label": "Calm", "shot": None, "zoom": 1.12, "motion": 1.0, "tempo": 1.0, "vivid": 1.12,
             "note": "One wide shot per line, gentle push-ins. Classic preschool TV pacing; the most "
                     "parent-trusted style and the research-backed choice for under-4s."},
    "lively": {"label": "Lively", "shot": (3.0, 4.5), "zoom": 1.4, "motion": 1.4, "tempo": 1.04, "vivid": 1.22,
               "note": "A new shot every 3-4.5 s, close-ups and reaction shots, livelier motion. A balance of energy and calm."},
    "rapid": {"label": "Rapid", "shot": (1.4, 2.8), "zoom": 1.55, "motion": 1.9, "tempo": 1.1, "vivid": 1.32,
              "note": "A new shot every 1.4-2.8 s, punch-ins on the beat, bouncy motion, vivid colour, faster music. "
                      "Highest moment-to-moment attention (the style of the biggest kids channels). Trade-off: very fast "
                      "pacing was linked to lower self-control right after viewing in 4-year-olds (Lillard & Peterson 2011)."},
}


def pace(name: str | None) -> dict:
    return {"id": name if name in PACES else "calm", **PACES.get(name or "", PACES["calm"])}


def band(name: str | None) -> dict:
    return {"id": name if name in AGE_BANDS else "preschool", **AGE_BANDS.get(name or "", AGE_BANDS["preschool"])}


# ---------------------------------------------------------------- the principles
# id, name, the evidence, and where the code applies it. Shown on the dashboard's Psychology page.
PRINCIPLES: list[dict] = [
    {"id": "ritual", "name": "Same opening, same goodbye",
     "why": "Predictable routines make young children feel safe and let them anticipate (and join in). Long-running "
            "preschool shows open and close the same way every time.",
     "how": "Every episode starts with the channel's theme jingle + hello ritual and ends with the goodbye song."},
    {"id": "participation", "name": "Ask, then wait",
     "why": "Direct questions followed by a real pause turn watching into doing; children who answered out loud "
            "showed more engagement and problem solving (Blue's Clues studies).",
     "how": "Question scenes get a timed pause (age-based, 1.8-3 s) with a gentle 'thinking' sound and a "
            "visual countdown; then the character celebrates the answer."},
    {"id": "repetition", "name": "Repeat with a twist",
     "why": "Children need many exposures to learn a word (fast mapping) and love to predict what comes next.",
     "how": "The key words of the episode are repeated 2-5 times (by age) in different contexts and recapped at the end."},
    {"id": "pacing", "name": "Calm pace, not frantic",
     "why": "Very fast-paced, fantastical cartoons measurably reduce preschoolers' self-control right after "
            "watching (Lillard & Peterson, Pediatrics 2011).",
     "how": "Minimum shot length per age band, soft transitions, no strobing, speech at a child-friendly speed."},
    {"id": "curiosity", "name": "Wonder questions, answered",
     "why": "A small information gap ('Why is the sky blue?') triggers curiosity; resolving it is rewarding. "
            "Unresolved cliffhangers cause anxiety in young children, so every gap closes in the same segment.",
     "how": "Each segment opens with a wonder question and answers it before the next one starts."},
    {"id": "characters", "name": "Friends they know",
     "why": "Children learn more from familiar characters they feel a bond with (parasocial relationships "
            "research, Calvert & Richards). Round shapes and big eyes ('baby schema') attract attention and warmth.",
     "how": "A fixed cast with stable looks, voices and catchphrases appears in every episode."},
    {"id": "peer", "name": "A learner like them",
     "why": "Children identify with a character who doesn't know yet, makes mistakes and tries again.",
     "how": "Pip asks the questions and gets things a bit wrong; the viewer gets to help."},
    {"id": "movement", "name": "Move your body",
     "why": "Embodied learning (acting out words and numbers) improves memory and gives a needed energy reset.",
     "how": "At least one 'stand up and move' break per episode (hop like a frog, stretch like a tree)."},
    {"id": "music", "name": "Sing it to remember it",
     "why": "Rhythm and rhyme build phonological awareness and melody makes facts stick.",
     "how": "A sing-along song in every episode with big on-screen words (karaoke), repeated chorus."},
    {"id": "dual", "name": "Say it and show it",
     "why": "Hearing a word while seeing the thing (dual coding) is how young children map words to meaning.",
     "how": "Counting, letters, colours and shapes appear on screen exactly when the word is spoken."},
    {"id": "mindset", "name": "Praise trying",
     "why": "Praising effort ('You kept trying!') rather than talent builds persistence (Dweck).",
     "how": "The Critic checks for effort praise and flags 'you're so smart' style praise."},
    {"id": "feelings", "name": "Name the feeling",
     "why": "Labelling emotions is the first step of self-regulation; children copy the coping they see.",
     "how": "Characters say how they feel and show a calm way to handle it (deep breath, ask for help)."},
    {"id": "humour", "name": "Silly surprises",
     "why": "Age-right humour (silly sounds, things in the wrong place) grabs and holds attention.",
     "how": "A gentle silly moment every couple of minutes; never mean jokes, never humiliation."},
    {"id": "windows", "name": "Mirrors and windows",
     "why": "Children everywhere should see their world (mirrors) and other worlds (windows).",
     "how": "Names, foods, festivals and places from every continent; no stereotypes; universal animal cast."},
    {"id": "colour", "name": "Bright, clear, safe colours",
     "why": "Saturated warm colours and strong figure/ground contrast are easiest for young eyes. Flashing over "
            "3 times a second can trigger photosensitive seizures.",
     "how": "Soft-saturated palettes, outlined characters, flash-safety check on every render."},
    {"id": "parentese", "name": "Warm, sing-song voice",
     "why": "Child-directed speech (higher pitch, slower, exaggerated melody) holds infants' and toddlers' attention.",
     "how": "Voices tuned slower with playful delivery; bedtime episodes get a slow, soft voice."},
    {"id": "winddown", "name": "End calm",
     "why": "A calm ending helps the transition away from the screen — parents notice and trust the channel.",
     "how": "Episodes close with a quiet recap and goodbye, not a hype teaser."},
]

# Dark patterns we refuse to use — the Safety gate and Critic enforce these.
NEVER = [
    "Fake cliffhangers or 'wait for the end' baiting",
    "Scary, gross or shocking thumbnails and titles; ALL-CAPS clickbait",
    "Asking kids to comment (comments are off on made-for-kids videos) or for personal information of any kind",
    "Toys, unboxing, brands or 'ask your parents to buy'",
    "Loud sudden noises, flashing lights, frantic cutting",
    "Dangerous things kids could copy (fire, sockets, medicine, climbing, eating non-food)",
    "Mean humour, name-calling, stereotypes, gendered 'boys/girls can't'",
    "Rewards for watching more ('watch 3 more videos to…')",
]

# ---------------------------------------------------------------- writer brief
def writer_brief(band_id: str) -> str:
    b = band(band_id)
    return (
        f"AUDIENCE: {b['label']}. {b['voice']}\n"
        f"- Sentences of at most {b['sentence']} words. Concrete words a {b['ages']}-year-old knows; explain any new word.\n"
        f"- Speak TO the child ('you'), warmly. About {b['interact_per_min']} interactions per minute: questions to "
        f"answer out loud ('Can you see it?', 'How many?'), 'say it with me', point, clap, count along.\n"
        f"- After a question, the scene kind is \"question\" and the NEXT scene celebrates the answer "
        f"('Yes! Three apples! Great counting!').\n"
        f"- Repeat each key word at least {b['repeat_key']} times across the episode, in different sentences.\n"
        "- Each segment opens with a wonder question and answers it in the same segment (no unresolved cliffhangers).\n"
        "- Praise effort and trying ('You kept going!'), never 'you're so smart'.\n"
        "- Characters name their feelings and show a calm way to handle them.\n"
        "- A gentle silly moment every couple of minutes (funny sound, something in the wrong place).\n"
        "- Inclusive world: names, foods, places and festivals from every continent, no stereotypes.\n"
        "- NEVER: scary/violent/gross things, danger kids could copy, brands/toys/buying, asking to "
        "comment, personal questions (name, address, school), mean jokes, 'boys/girls can't', fake cliffhangers.\n"
    )


# ---------------------------------------------------------------- script analysis (used by the Critic)
_EFFORT = re.compile(r"\b(you (kept|tried|did it|worked|practi[cs]ed|didn'?t give up)|great (try|trying|job|counting|"
                     r"singing|listening|thinking|helping)|keep trying|good try|well done|you can do it|try again)\b", re.I)
_FIXED_PRAISE = re.compile(r"\b(you'?re so (smart|clever|gifted)|so smart|genius)\b", re.I)
_FEEL = re.compile(r"\b(happy|sad|angry|mad|scared|worried|nervous|proud|excited|calm|frustrated|lonely|surprised|"
                   r"shy|brave|kind|grumpy|upset|cross|feel|feeling|feelings)\b", re.I)
_INTERACT = re.compile(r"(\?|\bsay it with me\b|\bcan you\b|\blet'?s\b|\bclap\b|\bpoint\b|\bcount with\b|"
                       r"\bjump\b|\bhop\b|\bstretch\b|\bwave\b|\bsing\b|\bshout\b|\btogether\b)", re.I)
_WORD = re.compile(r"[A-Za-z']+")


def syllables(word: str) -> int:
    w = word.lower().strip("'")
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def fk_grade(text: str) -> float:
    sents = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = _WORD.findall(text)
    if not sents or not words:
        return 0.0
    syl = sum(syllables(w) for w in words)
    return round(0.39 * len(words) / len(sents) + 11.8 * syl / len(words) - 15.59, 2)


def spoken_scenes(script: dict) -> list[dict]:
    return [sc for seg in script.get("segments", []) for sc in seg.get("scenes", [])]


def analyze(script: dict, band_id: str) -> dict:
    """Measurable child-psychology metrics for a script + the issues found."""
    b = band(band_id)
    scenes = spoken_scenes(script)
    text = " ".join(sc.get("text", "") for sc in scenes)
    words = _WORD.findall(text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    long = [s for s in sentences if len(_WORD.findall(s)) > b["sentence"] + 3]
    kinds = Counter(sc.get("kind", "line") for sc in scenes)
    seg_kinds = Counter(seg.get("kind", "") for seg in script.get("segments", []))
    est_min = estimate_minutes(script, band_id)
    interactions = len(_INTERACT.findall(text)) + kinds.get("question", 0)
    keys = [k.lower() for k in script.get("key_words", []) if k]
    low = text.lower()
    key_counts = {k: len(re.findall(r"\b" + re.escape(k) + r"\b", low)) for k in keys}
    issues = []
    if long:
        issues.append(f"{len(long)} sentence(s) too long for {b['label']} (max {b['sentence']} words), e.g. \"{long[0][:90]}\"")
    if est_min and interactions / est_min < b["interact_per_min"] * 0.7:
        issues.append(f"Too few interactions: {interactions} in ~{est_min:.0f} min (want {b['interact_per_min']}/min)")
    if kinds.get("question", 0) < 3:
        issues.append("Fewer than 3 'question' scenes with an answer pause")
    weak = [k for k, n in key_counts.items() if n < b["repeat_key"]]
    if weak:
        issues.append(f"Key words not repeated enough ({b['repeat_key']}x): " + ", ".join(weak[:5]))
    if "song" not in seg_kinds:
        issues.append("No sing-along song segment")
    if "movement" not in seg_kinds and not re.search(r"\b(stand up|jump|hop|stretch|wiggle|dance)\b", low):
        issues.append("No movement break")
    if "hello" not in seg_kinds or "goodbye" not in seg_kinds:
        issues.append("Missing the hello/goodbye ritual")
    if not _EFFORT.search(text):
        issues.append("No effort praise ('You kept trying!')")
    if _FIXED_PRAISE.search(text):
        issues.append("Uses fixed-ability praise ('so smart'); praise effort instead")
    if not _FEEL.search(text):
        issues.append("No feelings named")
    grade = fk_grade(text)
    if grade > b["fk_grade"] + 1.5:
        issues.append(f"Language too hard: reading grade {grade} (want ≤ {b['fk_grade'] + 1})")
    return {
        "words": len(words), "scenes": len(scenes), "est_minutes": round(est_min, 1),
        "avg_sentence": round(len(words) / max(1, len(sentences)), 1), "long_sentences": len(long),
        "questions": kinds.get("question", 0), "interactions": interactions,
        "interact_per_min": round(interactions / est_min, 2) if est_min else 0,
        "key_word_counts": key_counts, "fk_grade": grade,
        "segment_kinds": dict(seg_kinds), "effort_praise": bool(_EFFORT.search(text)),
        "feelings": len(_FEEL.findall(text)), "issues": issues,
    }


def score(metrics: dict) -> float:
    """0-10 from the measurable checks alone (the Critic blends this with the model's rubric)."""
    return round(max(0.0, 10.0 - 1.1 * len(metrics.get("issues", []))), 2)


def estimate_minutes(script: dict, band_id: str) -> float:
    """Spoken time at the band's speed + pauses + songs + rituals."""
    b = band(band_id)
    secs = 0.0
    for seg in script.get("segments", []):
        for sc in seg.get("scenes", []):
            n = len(_WORD.findall(sc.get("text", "")))
            if seg.get("kind") == "song" or sc.get("kind") == "sing":
                secs += max(2.4, n / 2.0)            # sung lines sit on a beat grid, ~2 words/s
            else:
                secs += n / b["wpm"] * 60 + 0.45
            if sc.get("kind") == "question":
                secs += b["pause"]
    return secs / 60
