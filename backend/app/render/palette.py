"""Colour palettes for episodes, from published research on kids' video colour.

Sources (fetched 6 Nov 2026):
  * Filmora / Wondershare, "Kids color palette" — 15 named palettes in 4 groups (playful, pastel, bold,
    educational) with mood + use. Advice: soft pastels for babies, toddlers and bedtime; bolder brights for
    older kids; 1-2 main colours + 2-3 supporting; a neutral (white, off-white, navy) for text and panels;
    colour-code topics so children can navigate; keep text legible on small screens.
    https://filmora.wondershare.com/video-creative-tips/kids-color-palette.html
  * The Straits Times, "Too fast, too colourful" (Mar 2026) — measured 10 dominant colours per frame (OKLCH) of
    popular kids' videos. Very saturated, all-hue palettes (Paw Patrol) are the most stimulating; calmer
    narrative shows (Bluey) use fewer, softer hues. Experts: bright colour isn't harmful in itself, balance
    matters; intense, flashing colour changes lead to sensory overload. Its three measured palettes are kept
    here as "real-show" references (the page doesn't label which show each came from).
    https://www.straitstimes.com/multimedia/graphics/2026/03/screen-time-kids-video-analysis/index.html

How it's used: one palette per episode (Filmora's restraint), picked from the category and the age band; calm
and bedtime segments switch to the pastel companion; saturation is capped by age (Straits Times). The palette
colours the cards, counting numbers, sing-along highlight, chapter banners, name tags, logo, end card and
thumbnail, and gives the sets a gentle colour wash.
"""
from __future__ import annotations

import colorsys

FILMORA = "Filmora (Wondershare) kids colour palettes"
ST = "The Straits Times kids' video colour analysis (2026)"

PALETTES: dict[str, dict] = {
    # ---- playful
    "rainbow_playground": {"name": "Rainbow Playground Fun", "group": "playful", "mood": "Joyful, energetic",
                           "colors": ["#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff", "#f2f2f2"], "source": FILMORA},
    "candy_shop": {"name": "Candy Shop Adventure", "group": "playful", "mood": "Sweet, whimsical, lighthearted",
                   "colors": ["#ff9aa2", "#ffdac1", "#f7f3c7", "#b5ead7", "#c7ceff"], "source": FILMORA},
    "birthday_balloon": {"name": "Birthday Balloon Bash", "group": "playful", "mood": "Festive, celebratory",
                         "colors": ["#ff5d8f", "#ffb547", "#35d0ba", "#5b5f97", "#ffffff"], "source": FILMORA},
    "toy_box": {"name": "Toy Box Surprise", "group": "playful", "mood": "Curious, playful, adventurous",
                "colors": ["#ff9f1c", "#ffbf69", "#2ec4b6", "#cbf3f0", "#293241"], "source": FILMORA},
    # ---- pastel
    "dreamy_nursery": {"name": "Dreamy Nursery Pastels", "group": "pastel", "mood": "Gentle, soothing, cozy",
                       "colors": ["#ffe5ec", "#ffd6a5", "#fdffb6", "#caffbf", "#bdb2ff"], "source": FILMORA},
    "cotton_candy": {"name": "Cotton Candy Skies", "group": "pastel", "mood": "Airy, magical, dreamy",
                     "colors": ["#ffafcc", "#ffc8dd", "#cdb4db", "#a2d2ff", "#bde0fe"], "source": FILMORA},
    "storybook_naptime": {"name": "Storybook Naptime", "group": "pastel", "mood": "Warm, comforting, nostalgic",
                          "colors": ["#f4f1de", "#e07a5f", "#f2cc8f", "#81b29a", "#3d405b"], "source": FILMORA},
    "gentle_dino": {"name": "Gentle Dino Friends", "group": "pastel", "mood": "Friendly, calm, imaginative",
                    "colors": ["#d4f8e8", "#f6f7d7", "#fce1e4", "#c1e3ff", "#90a955"], "source": FILMORA},
    # ---- bold
    "arcade_hero": {"name": "Arcade Hero Energy", "group": "bold", "mood": "High-energy, bold, dynamic",
                    "colors": ["#ff006e", "#ffbe0b", "#3a86ff", "#06d6a0", "#000814"], "source": FILMORA},
    "superhero_pop": {"name": "Superhero Comic Pop", "group": "bold", "mood": "Brave, bold, action-packed",
                      "colors": ["#ff1654", "#ff9f1c", "#247ba0", "#70c1b3", "#f7fff7"], "source": FILMORA},
    "space_explorer": {"name": "Space Explorer Night", "group": "bold", "mood": "Mysterious, adventurous, futuristic",
                       "colors": ["#0f172a", "#1e293b", "#38bdf8", "#22c55e", "#eab308"], "source": FILMORA},
    # ---- educational
    "alphabet_classroom": {"name": "Alphabet Classroom Brights", "group": "educational", "mood": "Smart, energetic, inviting",
                           "colors": ["#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93"], "source": FILMORA},
    "science_lab": {"name": "Science Lab Spark", "group": "educational", "mood": "Curious, inventive, experimental",
                    "colors": ["#00f5d4", "#9b5de5", "#fee440", "#f15bb5", "#2d3142"], "source": FILMORA},
    "art_time": {"name": "Art Time Rainbow Mix", "group": "educational", "mood": "Creative, expressive, playful",
                 "colors": ["#ff6f59", "#ffcc5c", "#88d8b0", "#6c5b7b", "#f8f8f8"], "source": FILMORA},
    "music_room": {"name": "Music Room Rhythm", "group": "educational", "mood": "Upbeat, rhythmic, friendly",
                   "colors": ["#ff4d6d", "#ffb3c1", "#3c6e71", "#284b63", "#f5f3f4"], "source": FILMORA},
    # ---- measured on real kids' videos (OKLCH dominant colours, chroma >= 0.08)
    "st_real_a": {"name": "Real-show palette A", "group": "measured", "mood": "Natural, calm: teals, sage, plum, rust",
                  "colors": ["#69506c", "#47a98f", "#a2ab7a", "#3f93ae", "#bcdbae", "#2f7687", "#67cbbf", "#a36c3e",
                             "#803726", "#074960"], "source": ST},
    "st_real_b": {"name": "Real-show palette B", "group": "measured", "mood": "Sky blue, warm skin tones, red accent",
                  "colors": ["#10ade0", "#5d525c", "#98cbd6", "#7b7d8e", "#bf2310", "#e9adcb", "#51b8db", "#491f1c",
                             "#ecf1f4", "#d3986b"], "source": ST},
    "st_real_c": {"name": "Real-show palette C", "group": "measured", "mood": "Sunny: sky blue, sand, leaf green, violet",
                  "colors": ["#13aee0", "#fcd995", "#4dbdda", "#e3bc81", "#335437", "#72987a", "#8fc9d5", "#b86e2f",
                             "#9877d0", "#c9dae9"], "source": ST},
}

# Filmora's use-cases, mapped to our categories (one palette per episode = colour-coded topics)
FOR_CATEGORY = {
    "numbers": "alphabet_classroom", "abc": "alphabet_classroom", "colors_shapes": "art_time",
    "animals": "st_real_c", "stories": "storybook_naptime", "books": "storybook_naptime", "bedtime": "cotton_candy",
    "science": "science_lab", "space": "space_explorer", "dinosaurs": "gentle_dino", "vehicles": "rainbow_playground",
    "habits": "candy_shop", "feelings": "candy_shop", "world": "toy_box", "music_move": "music_room",
    "puzzles": "toy_box",
}
# softer for the youngest, bolder for big kids (Filmora); the measured real-show palettes are a calm middle
FOR_BAND = {"toddler": "dreamy_nursery"}
BIG_SWAP = {"rainbow_playground": "superhero_pop", "toy_box": "arcade_hero", "candy_shop": "birthday_balloon"}
CALM_COMPANION = {"pastel": None, "measured": "storybook_naptime"}        # calm/bedtime segments
CALM_DEFAULT = "cotton_candy"
# Saturation ceiling by age (Straits Times: high chroma + many hues = most stimulating; balance matters)
VIVID_CAP = {"toddler": 1.0, "preschool": 1.14, "early": 1.24, "big": 1.32}
CALM_KINDS = ("calm",)

CURRENT: dict = {"id": "rainbow_playground", "calm": CALM_DEFAULT, "band": "preschool"}


# ---------------------------------------------------------------- colour maths
def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _hsv(c):
    return colorsys.rgb_to_hsv(*(v / 255 for v in c))


def _lum(c) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
    r, g, b = c
    return .2126 * ch(r) + .7152 * ch(g) + .0722 * ch(b)


def contrast(a, b) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


def _deepen(c, k=.0):
    h, s, v = _hsv(c)
    s, v = min(1, s + k * .35), max(0, v - k * .4)
    return tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, s, v))


def _vivid(c, minimum_s=.55, minimum_v=.78):
    """Pastels lifted to a readable accent (same hue), used for text/frames when the palette is very soft."""
    h, s, v = _hsv(c)
    return tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, max(s, minimum_s), max(v, minimum_v)))


def roles(pid: str) -> dict:
    """Split a palette into roles: accents (chromatic, strongest first), light (panel/wash), dark (ink/text)."""
    cols = [rgb(h) for h in PALETTES.get(pid, PALETTES["rainbow_playground"])["colors"]]
    chroma = [c for c in cols if _hsv(c)[1] >= .18 and .3 <= _hsv(c)[2]]
    neutral = [c for c in cols if c not in chroma]
    light = max(cols, key=_lum)
    dark = min(cols, key=_lum)
    if not chroma:
        chroma = cols
    soft = PALETTES.get(pid, {}).get("group") == "pastel" or max(_hsv(c)[1] for c in chroma) < .45
    accents = sorted(chroma, key=lambda c: -(_hsv(c)[1] * _hsv(c)[2]))
    if soft:
        accents = [_vivid(c) for c in accents]
    return {"accents": accents[:5], "light": light, "dark": dark if _lum(dark) < .2 else (45, 40, 70),
            "neutral": neutral, "soft": soft}


# ---------------------------------------------------------------- choice
def choose(category: str | None, band: str | None, fixed: str | None = None) -> str:
    if fixed and fixed in PALETTES:
        return fixed
    if band in FOR_BAND and category not in ("space",):
        return FOR_BAND[band]
    pid = FOR_CATEGORY.get(category or "", "rainbow_playground")
    if band == "big":
        pid = BIG_SWAP.get(pid, pid)
    if pid == "space_explorer" and band in ("toddler", "preschool"):
        pid = "cotton_candy"                     # dark neon is for older kids; little ones get a dreamy sky
    return pid


def calm_for(pid: str) -> str:
    g = PALETTES[pid]["group"]
    if g == "pastel":
        return pid
    return CALM_COMPANION.get(g) or CALM_DEFAULT


def set_current(pid: str, band: str = "preschool") -> str:
    pid = pid if pid in PALETTES else "rainbow_playground"
    CURRENT.update(id=pid, calm=calm_for(pid), band=band)
    return pid


def active(calm: bool = False) -> dict:
    return roles(CURRENT["calm"] if calm else CURRENT["id"])


def accent(i: int, calm: bool = False):
    a = active(calm)["accents"]
    return a[i % len(a)]


def primary(calm: bool = False):
    return accent(0, calm)


def highlight(calm: bool = False):
    """The sing-along highlight: the palette's sunniest strong colour (yellow/orange if it has one)."""
    a = active(calm)["accents"]
    warm = [c for c in a if .07 <= _hsv(c)[0] <= .19 and _hsv(c)[2] > .8]
    return max(warm, key=lambda c: _hsv(c)[1] * _hsv(c)[2]) if warm else a[0]


def on_light(c, bg=(255, 253, 245), need=1.6):
    """A colour that still shows on a cream card (frames, big numerals): deepened just enough."""
    for k in (0, .15, .3, .45, .6):
        d = _deepen(c, k)
        if contrast(d, bg) >= need:
            return d
    return _deepen(c, .75)


def button(calm: bool = False):
    """A fill that white text reads on (pills, badges): the primary, deepened until contrast >= 3."""
    acc = active(calm)["accents"]
    good = [c for c in acc if contrast(c, (255, 255, 255)) >= 3]
    if good:
        return good[0]
    c = max(acc, key=lambda x: contrast(x, (255, 255, 255)))     # the palette colour closest to readable, deepened
    for k in (0, .2, .35, .5, .65):
        d = _deepen(c, k)
        if contrast(d, (255, 255, 255)) >= 3:
            return d
    return _deepen(c, .8)


def wash(calm: bool = False):
    """A very soft grade colour for the sets: mostly the warm grade, tinted 22% toward the palette's light."""
    light = active(calm)["light"]
    warm = (255, 247, 236)
    return tuple(int(w * .78 + l * .22) for w, l in zip(warm, light))


def vivid_cap(band: str | None, calm: bool = False) -> float:
    return 1.0 if calm else VIVID_CAP.get(band or "preschool", 1.14)


def catalog() -> list[dict]:
    return [{"id": k, **v, "for": sorted(c for c, p in FOR_CATEGORY.items() if p == k)} for k, v in PALETTES.items()]
