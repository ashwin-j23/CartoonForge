"""The recurring cast. Original characters, drawn in code (render/characters.py), so their look never drifts.

Animals on purpose: they cross every culture, language and skin tone, so a child in Lagos, Lima or Lahore can
see themselves in the same friend. Each has one clear trait (easy for a 3-year-old to predict), a catchphrase
(ritual + repetition) and a fixed voice (parasocial bond).
"""
from __future__ import annotations

CAST: dict[str, dict] = {
    "hoppy": {
        "name": "Hoppy", "species": "frog", "role": "star",
        "look": "a bright aqua tree frog with big eyes on top of his head, a wide grin, round toe pads and an orange scarf",
        "personality": "THE MAIN CHARACTER: brave, bouncy and curious; every adventure is his, he leaps in first, "
                       "tries, wobbles, never gives up, and always asks the child to help",
        "catchphrase": "Hop to it, friends!",
        "colors": {"body": (60, 196, 160), "accent": (255, 140, 50), "belly": (232, 250, 205)},
        "voice": "kokoro:am_puck*0.5+am_liam*0.5", "gender": "m",
    },
    "sunny": {
        "name": "Sunny", "species": "sun", "role": "host",
        "look": "a smiling sun with soft rays who lives in the sky of every set",
        "personality": "the warm host; welcomes everyone, sets up each game, cheers kids on",
        "catchphrase": "Hello, hello, little sprouts!",
        "colors": {"body": (255, 205, 60), "accent": (255, 150, 40), "cheek": (255, 130, 110)},
        "voice": "kokoro:af_heart*0.5+af_sky*0.5", "gender": "f",
    },
    "pip": {
        "name": "Pip", "species": "penguin", "role": "learner",
        "look": "a small round blue penguin chick with a white tummy and orange feet",
        "personality": "curious, asks 'why?', gets things a little wrong and tries again (the viewer helps)",
        "catchphrase": "Ooh! Why is that?",
        "colors": {"body": (70, 140, 230), "accent": (255, 160, 40), "belly": (250, 250, 255)},
        "voice": "kokoro:am_puck*0.7+am_echo*0.3", "gender": "m",
    },
    "mimi": {
        "name": "Mimi", "species": "bunny", "role": "helper",
        "look": "a pink bunny with long floppy ears and a yellow flower",
        "personality": "kind and musical; leads the songs, helps friends with their feelings",
        "catchphrase": "Let's sing it together!",
        "colors": {"body": (255, 170, 200), "accent": (255, 225, 90), "belly": (255, 235, 242)},
        "voice": "kokoro:af_sky", "gender": "f",
    },
    "bo": {
        "name": "Bo", "species": "dinosaur", "role": "gentle giant",
        "look": "a big round green dinosaur with soft back spikes",
        "personality": "big, gentle and a bit clumsy; has big feelings and learns to handle them; silly moments",
        "catchphrase": "Oopsie-daisy!",
        "colors": {"body": (110, 200, 110), "accent": (250, 210, 80), "belly": (215, 245, 190)},
        "voice": "kokoro:bm_lewis", "gender": "m",
    },
    "zuzu": {
        "name": "Zuzu", "species": "fox", "role": "explorer",
        "look": "an orange fox with a white-tipped tail and a little backpack",
        "personality": "adventurous; visits places, foods and festivals all over the world",
        "catchphrase": "Pack your bags, let's go!",
        "colors": {"body": (250, 140, 60), "accent": (90, 170, 220), "belly": (255, 245, 230)},
        "voice": "kokoro:af_nova", "gender": "f",
    },
    "nana": {
        "name": "Nana Owl", "species": "owl", "role": "storyteller",
        "look": "a wise purple owl with round glasses",
        "personality": "tells the stories and fables, calm and cosy; bedtime episodes are hers",
        "catchphrase": "Snuggle in, it's story time.",
        "colors": {"body": (150, 110, 200), "accent": (255, 200, 90), "belly": (230, 215, 250)},
        "voice": "kokoro:bf_emma", "gender": "f",
    },
}

SPEAKERS = list(CAST)
STAR = "hoppy"          # the main character: in every episode, at the centre of every story


BIG = ("lion", "bear", "giant", "elephant", "whale", "dragon", "king", "tiger", "crocodile", "wolf", "ogre", "bull")
SMALL = ("mouse", "bird", "ant", "bee", "butterfly", "chick", "sparrow", "frog", "fairy", "squirrel", "rabbit", "hare")
GUEST_VOICES = {   # never the main cast's voices, so story characters always sound like someone new
    ("f", "child"): ["kokoro:af_sky*0.6+af_nova*0.4", "kokoro:af_jessica", "kokoro:af_nova"],
    ("f", "adult"): ["kokoro:af_bella", "kokoro:af_nicole", "kokoro:bf_isabella", "kokoro:af_sarah", "kokoro:af_kore"],
    ("f", "old"): ["kokoro:bf_alice", "kokoro:af_sarah", "kokoro:bf_lily"],
    ("m", "child"): ["kokoro:am_echo", "kokoro:am_puck"],
    ("m", "adult"): ["kokoro:am_michael", "kokoro:am_eric", "kokoro:bm_fable", "kokoro:am_liam", "kokoro:bm_daniel"],
    ("m", "old"): ["kokoro:bm_george", "kokoro:am_onyx"],
}


def guest_profile(g: dict) -> tuple[str, float]:
    """(voice id, pitch factor) for a story character, stable per character (hash of its id + name)."""
    import hashlib
    words = f"{g.get('species', '')} {g.get('name', '')} {g.get('role', '')}".lower()
    gender = "f" if str(g.get("gender", "")).lower().startswith("f") else "m"
    age = str(g.get("age", "adult")).lower()
    age = age if age in ("child", "adult", "old") else "adult"
    pool = GUEST_VOICES[(gender, age)]
    h = int(hashlib.md5((g.get("id", "") + g.get("name", "")).encode()).hexdigest()[:6], 16)
    voice = pool[h % len(pool)]
    pitch = 1.0
    if any(w in words for w in BIG):
        voice, pitch = ("kokoro:am_fenrir" if gender == "m" else "kokoro:af_kore"), 0.93
    elif any(w in words for w in SMALL):
        pitch = 1.1
    elif age == "child":
        pitch = 1.05
    elif age == "old":
        pitch = 0.96
    if g.get("voice"):                       # saved in the character library: always the same voice
        voice = str(g["voice"])
    if g.get("pitch"):
        try:
            pitch = max(.8, min(1.25, float(g["pitch"])))
        except (TypeError, ValueError):
            pass
    return voice, pitch


def voice_for(char_id: str, overrides: dict | None = None, lang: str = "en", guests: dict | None = None) -> str:
    """The character's voice in the episode language (editions use a same-gender voice of that language)."""
    if char_id in CAST and not (overrides or {}).get(char_id):
        try:                                  # a voice picked for a core character on the Characters page
            from ..db import get_db
            v = ((get_db().get_setting("core_overrides") or {}).get(char_id) or {}).get("voice")
            if v:
                overrides = {**(overrides or {}), char_id: v}
        except Exception:  # noqa: BLE001
            pass
    if guests and char_id in guests and char_id not in CAST:
        g = guests[char_id]
        if lang and lang != "en":
            from .languages import voice_for_lang
            return voice_for_lang(lang, "f" if str(g.get("gender", "")).startswith("f") else "m", char_id)
        return guest_profile(g)[0]
    c = CAST.get(char_id) or CAST["sunny"]
    if lang and lang != "en":
        from .languages import voice_for_lang
        return voice_for_lang(lang, c["gender"], char_id)
    return (overrides or {}).get(char_id) or c["voice"]


def bible() -> str:
    """Cast description handed to the Writer. Hoppy is the star, so the brief says so first."""
    star = CAST[STAR]
    return (f"MAIN CHARACTER: {star['name']} (id {STAR}) is the star of the show. He is on screen in EVERY segment, the "
            f"adventure or problem of each episode is HIS, he speaks often (about a third of the lines that aren't "
            f"narration or songs), the episode opens on HIM in the middle of the action (no greeting or roll call), and he "
            "always invites the child to help him. The other friends support him.\n") + "\n".join(f"- {cid}: {c['name']}, {c['look']}. Role: {c['role']}; {c['personality']}. "
                     f"Catchphrase: \"{c['catchphrase']}\"" for cid, c in CAST.items())
