"""Character designer: draws ANY character a story needs from a small design spec.

The Writer describes each story character as JSON (kind, species, colours, ears, face, tail, extras, outfit, hair,
skin, age). Presets fill everything it leaves out, so "a wolf", "an old king", "a girl from Lagos" or "a friendly
dragon" all come out in the same round, big-eyed, picture-book style as the main cast: same toon kit (contour
weights, violet form shadows, rim light, eyes, brows and mouths) as render/characters.py.

Every species has its own silhouette feature (mane, trunk, long neck, hump, fan tail, shell, coil, antlers...) so
children can tell them apart from the outline alone.

spec -> sprite(spec_json, height, mouth, eyes, emotion, arms)
"""
from __future__ import annotations

import json
import math
from functools import lru_cache

from PIL import Image, ImageDraw

from .common import OUT, darken, lighten
from . import characters as base
from .characters import MOUTH, MOUTH_DARK, TONGUE, Toon, _bez, eye, mouth as draw_mouth, nose, two_arms

# ---------------------------------------------------------------- presets
SKINS = {"deep": (110, 70, 45), "brown": (150, 100, 65), "tan": (200, 150, 105), "light": (240, 200, 165),
         "pale": (250, 220, 200), "olive": (190, 160, 110)}
HAIRS = {"black": (40, 35, 45), "brown": (110, 70, 40), "blonde": (240, 200, 100), "red": (200, 90, 50),
         "grey": (190, 190, 200), "white": (245, 245, 250)}

SPECIES = {
    # animals: main colour, belly, ears, face, tail, extras
    "fox": ((240, 130, 60), (255, 245, 230), "pointy", "muzzle", "bushy", []),
    "wolf": ((140, 145, 165), (225, 228, 235), "pointy", "muzzle", "bushy", []),
    "dog": ((205, 155, 105), (250, 235, 215), "floppy", "muzzle", "thin", []),
    "cat": ((245, 165, 90), (255, 240, 225), "pointy", "flat", "thin", ["whiskers"]),
    "lion": ((245, 195, 90), (255, 240, 200), "round", "muzzle", "thin", ["mane"]),
    "tiger": ((250, 150, 50), (255, 245, 230), "round", "muzzle", "thin", ["stripes", "whiskers"]),
    "bear": ((150, 100, 70), (225, 190, 150), "round", "muzzle", "none", []),
    "rabbit": ((235, 225, 220), (255, 250, 248), "long", "flat", "none", ["whiskers"]),
    "hare": ((200, 160, 120), (245, 230, 210), "long", "flat", "none", ["whiskers"]),
    "mouse": ((175, 175, 190), (240, 230, 235), "big_round", "flat", "thin", ["whiskers"]),
    "pig": ((255, 185, 200), (255, 220, 228), "pointy", "snout", "curly", []),
    "cow": ((250, 250, 250), (255, 215, 220), "round", "snout", "thin", ["spots", "horns"]),
    "horse": ((180, 120, 80), (230, 200, 170), "pointy", "muzzle", "thin", ["mane"]),
    "donkey": ((160, 155, 165), (225, 220, 225), "long", "muzzle", "thin", []),
    "goat": ((235, 230, 220), (250, 248, 240), "floppy", "muzzle", "thin", ["horns"]),
    "sheep": ((250, 250, 250), (255, 255, 255), "floppy", "flat", "none", ["wool"]),
    "elephant": ((165, 175, 200), (200, 208, 225), "elephant", "trunk", "thin", []),
    "monkey": ((165, 115, 75), (240, 210, 175), "round_side", "flat", "curly", []),
    "giraffe": ((250, 200, 90), (255, 235, 180), "round", "muzzle", "thin", ["spots", "horns"]),
    "zebra": ((250, 250, 250), (255, 255, 255), "pointy", "muzzle", "thin", ["stripes", "mane"]),
    "crocodile": ((100, 175, 95), (210, 235, 170), "none", "long_snout", "thick", ["scales"]),
    "frog": ((110, 200, 95), (210, 245, 180), "none", "flat", "none", ["frog_eyes"]),
    "tortoise": ((120, 175, 100), (220, 235, 170), "none", "flat", "none", ["shell"]),
    "turtle": ((90, 180, 160), (215, 240, 200), "none", "flat", "none", ["shell"]),
    "owl": ((160, 120, 90), (235, 215, 185), "tufts", "beak", "none", ["wings"]),
    "bird": ((90, 170, 240), (230, 240, 255), "none", "beak", "none", ["wings"]),
    "crow": ((70, 70, 95), (120, 120, 150), "none", "beak", "none", ["wings"]),
    "duck": ((255, 220, 70), (255, 245, 190), "none", "duck_bill", "none", ["wings"]),
    "hen": ((240, 230, 215), (255, 250, 240), "none", "beak", "none", ["wings", "comb"]),
    "rooster": ((220, 120, 60), (250, 220, 160), "none", "beak", "none", ["wings", "comb"]),
    "peacock": ((60, 140, 200), (120, 200, 190), "none", "beak", "none", ["wings", "comb"]),
    "ant": ((180, 70, 60), (220, 120, 100), "antennae", "flat", "none", []),
    "grasshopper": ((140, 210, 90), (210, 240, 160), "antennae", "flat", "none", ["wings"]),
    "bee": ((255, 210, 60), (255, 235, 150), "antennae", "flat", "none", ["stripes", "wings"]),
    "butterfly": ((200, 140, 230), (240, 210, 250), "antennae", "flat", "none", ["wings"]),
    "fish": ((255, 150, 70), (255, 220, 180), "none", "flat", "fish", ["fins"]),
    "whale": ((90, 130, 200), (210, 225, 245), "none", "flat", "fish", ["fins"]),
    "dragon": ((120, 200, 150), (230, 245, 200), "horns", "long_snout", "thick", ["wings", "scales"]),
    "unicorn": ((250, 245, 255), (255, 240, 250), "pointy", "muzzle", "thin", ["mane", "unicorn_horn"]),
    "squirrel": ((200, 120, 60), (245, 215, 180), "pointy", "flat", "bushy", []),
    "deer": ((190, 130, 80), (245, 225, 200), "pointy", "muzzle", "none", ["antlers", "spots"]),
    "panda": ((250, 250, 250), (255, 255, 255), "round_dark", "muzzle", "none", ["panda"]),
    "penguin": ((70, 75, 100), (250, 250, 255), "none", "beak", "none", ["wings"]),
    "snake": ((120, 190, 80), (220, 240, 160), "none", "flat", "thick", ["scales"]),
    "kangaroo": ((200, 140, 90), (240, 210, 175), "long", "muzzle", "thick", []),
    "camel": ((215, 175, 120), (240, 215, 175), "round", "muzzle", "thin", []),
}
HUMAN_WORDS = ("human", "person", "boy", "girl", "man", "woman", "king", "queen", "prince", "princess", "child",
               "farmer", "giant", "old", "grandma", "grandpa", "mother", "father", "baker", "sailor", "wizard",
               "witch", "fairy", "hero", "knight", "merchant", "fisherman", "teacher", "monk", "chief", "emperor")
OUTFIT_FOR = {"king": "crown", "queen": "crown", "prince": "crown", "princess": "crown", "emperor": "crown",
              "wizard": "wizard_hat", "witch": "wizard_hat", "sailor": "cap", "farmer": "straw_hat",
              "knight": "helmet", "fairy": "wings", "baker": "chef_hat", "fisherman": "cap", "monk": "robe",
              "chief": "feathers", "merchant": "turban"}

# Per-species silhouette features used by the drawer (the SPECIES table above stays the public preset list).
#   plan: mammal | bird | bug | fish | snake | frog | shell | croc
#   build: chubby | normal | slim      ear/muzzle/tail: drawing variants       feet: paw | hoof | sock | webbed
LOOK = {
    "fox": dict(ears="fox", muzzle="fox", tail="fox", feet="sock", ruff=True),
    "wolf": dict(ears="pointy", muzzle="long", tail="bushy", ruff=True, brow_mark=True),
    "dog": dict(ears="floppy", muzzle="dog", tail="wag", patch=True),
    "cat": dict(ears="cat", muzzle="cat", tail="cat", forehead=True),
    "lion": dict(build="chubby", ears="round", muzzle="cat", tail="tuft", mane="lion"),
    "tiger": dict(build="chubby", ears="round", muzzle="cat", tail="striped", forehead=True),
    "bear": dict(build="chubby", ears="round", muzzle="bear", tail="none"),
    "panda": dict(build="chubby", ears="round_dark", muzzle="bear", tail="none", limbs=(55, 52, 62)),
    "rabbit": dict(ears="long", muzzle="bunny", tail="puff"),
    "hare": dict(ears="long", muzzle="bunny", tail="puff", ear_tips=True),
    "mouse": dict(ears="big_round", muzzle="mouse", tail="mouse", head=(21, 18)),
    "pig": dict(build="chubby", ears="pig", muzzle="pig", tail="curly"),
    "cow": dict(build="chubby", ears="side", muzzle="cow", tail="tuft", feet="hoof", horns="cow"),
    "horse": dict(ears="small_pointy", muzzle="horse", tail="hair", feet="hoof", mane="horse", head=(19, 20)),
    "donkey": dict(ears="donkey", muzzle="horse", tail="tuft", feet="hoof", mane="short", head=(19, 20)),
    "unicorn": dict(ears="small_pointy", muzzle="horse", tail="rainbow", feet="hoof", mane="rainbow", head=(19, 20)),
    "zebra": dict(ears="small_pointy", muzzle="horse", tail="tuft", feet="hoof", mane="zebra", head=(19, 20)),
    "goat": dict(ears="side", muzzle="horse", tail="puff", feet="hoof", horns="goat", beard=True, head=(19, 19)),
    "sheep": dict(build="chubby", ears="side", muzzle="sheep", tail="none", feet="hoof", wool=True),
    "elephant": dict(build="chubby", ears="elephant", muzzle="trunk", tail="tuft", head=(22, 19)),
    "monkey": dict(ears="monkey", muzzle="monkey", tail="monkey"),
    "giraffe": dict(build="slim", ears="side", muzzle="horse", tail="tuft", feet="hoof", neck=True, horns="ossicone",
                    head=(16, 15)),
    "kangaroo": dict(build="slim", ears="pointy_tall", muzzle="long", tail="thick", pouch=True, big_feet=True),
    "camel": dict(ears="side", muzzle="horse", tail="tuft", feet="hoof", hump=True, sleepy_lids=True, head=(19, 19)),
    "squirrel": dict(ears="squirrel", muzzle="cat", tail="squirrel", head=(20, 17.5)),
    "deer": dict(build="slim", ears="side_big", muzzle="horse", tail="puff", feet="hoof", antlers=True, head=(19, 18)),
    "dragon": dict(build="chubby", ears="fin", muzzle="dragon", tail="dragon", plates=True, horns="dragon", wings="bat"),
    "crocodile": dict(plan="croc", build="chubby", tail="thick"),
    "frog": dict(plan="frog"),
    "tortoise": dict(plan="shell", shell=(150, 110, 70)),
    "turtle": dict(plan="shell", shell=(70, 140, 110)),
    "snake": dict(plan="snake"),
    "owl": dict(plan="bird", tufts=True, disc=True),
    "bird": dict(plan="bird", crest="songbird"),
    "crow": dict(plan="bird", crest="crow", beak_col=(70, 70, 80)),
    "duck": dict(plan="bird", bill=True, crest="duck"),
    "hen": dict(plan="bird", comb="small", tail_feathers="hen"),
    "rooster": dict(plan="bird", comb="big", tail_feathers="rooster"),
    "peacock": dict(plan="bird", crest="peacock", fan=True),
    "penguin": dict(plan="bird", mask=True, flipper=True),
    "ant": dict(plan="bug", bug="ant"),
    "bee": dict(plan="bug", bug="bee"),
    "butterfly": dict(plan="bug", bug="butterfly"),
    "grasshopper": dict(plan="bug", bug="grasshopper"),
    "fish": dict(plan="fish"),
    "whale": dict(plan="fish", whale=True),
}


def normalize(spec: dict) -> dict:
    """Fill a partial design with presets so the drawer always has every field."""
    sp = dict(spec or {})
    species = str(sp.get("species") or sp.get("name") or "").lower()
    words = species + " " + str(sp.get("role", "")).lower() + " " + str(sp.get("name", "")).lower()
    kind = sp.get("kind")
    if kind not in ("animal", "human"):
        kind = "human" if any(w in words for w in HUMAN_WORDS) and not any(k in words for k in SPECIES) else "animal"
    sp["kind"] = kind
    if kind == "animal":
        key = next((k for k in SPECIES if k in species), None) or next((k for k in SPECIES if k in words), "bear")
        main, belly, ears, face, tail, extras = SPECIES[key]
        sp.setdefault("species", key)
        sp["_key"] = key
        sp["main"] = _col(sp.get("colors", {}).get("main")) or main
        sp["belly"] = _col(sp.get("colors", {}).get("belly")) or belly
        sp.setdefault("ears", ears)
        sp.setdefault("face", face)
        sp.setdefault("tail", tail)
        sp["extras"] = list(dict.fromkeys(list(sp.get("extras") or []) + extras))
    else:
        sp["skin_rgb"] = _col(sp.get("skin")) or SKINS.get(str(sp.get("skin", "")).lower(), SKINS["tan"])
        sp["hair_rgb"] = _col(sp.get("hair_color")) or HAIRS.get(str(sp.get("hair_color", "")).lower(), HAIRS["black"])
        old_man = str(sp.get("age", "")).lower() == "old" and str(sp.get("gender", "")).lower().startswith("m")
        sp.setdefault("hair", "bald" if old_man else "short")
        sp["main"] = _col(sp.get("colors", {}).get("main")) or (90, 150, 230)
        sp["belly"] = _col(sp.get("colors", {}).get("belly")) or lighten(sp["main"], .5)
        if not sp.get("outfit"):
            sp["outfit"] = next((o for w, o in OUTFIT_FOR.items() if w in words), "none")
        sp["_words"] = words
    sp["accent"] = _col(sp.get("colors", {}).get("accent")) or (255, 200, 60)
    age = str(sp.get("age", "adult")).lower()
    sp["age"] = age if age in ("child", "adult", "old") else "adult"
    if "giant" in words:
        sp["size"] = 1.35
    sp.setdefault("size", {"child": .82, "adult": 1.0, "old": .95}[sp["age"]])
    return sp


def _col(v):
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return tuple(int(x) for x in v[:3])
    if isinstance(v, str) and v.startswith("#") and len(v) == 7:
        return tuple(int(v[i:i + 2], 16) for i in (1, 3, 5))
    from .common import COLORS
    return COLORS.get(str(v).lower()) if v else None


INNER_EAR = (255, 175, 190)
NOSE = (62, 44, 62)
HOOF = (110, 80, 75)
SKIN_SHADOW = (190, 95, 100, 255)       # warm shadow for skin (violet would turn skin grey)


def _iris(main):
    """Iris colour that suits the body colour but is always warm and readable."""
    r, g, b = main[:3]
    if g > r and g > b:
        return (120, 80, 40)
    if b > r:
        return (60, 70, 140)
    return (110, 65, 40)


def _brow_col(main):
    return darken(main, .5) if sum(main[:3]) < 600 else (150, 130, 140)


# ================================================================= animals
class _A:
    """Per-drawing context for an animal."""

    def __init__(self, k: Toon, sp: dict):
        self.k, self.sp = k, sp
        self.key = sp.get("_key") or sp.get("species")
        self.look = dict(LOOK.get(self.key, {}))
        self.m, self.b, self.acc = sp["main"], sp["belly"], sp["accent"]
        self.ex = set(sp["extras"])
        build = self.look.get("build", "normal")
        self.build = build
        hrx, hry = self.look.get("head", (23.5, 19.5) if build == "chubby" else (22, 18.5))
        self.hrx, self.hry = hrx, hry
        self.hy = 40.5
        if self.look.get("neck"):
            self.hy = 24.5
        if self.look.get("mane") == "lion":
            self.hy = 41.5
        self.ey = self.hy - 1.5
        self.dark = darken(self.m, .2)
        self.limbs = self.look.get("limbs") or self.m


def _ears(a: _A, front=False):
    k, m, sp = a.k, a.m, a.sp
    e = a.look.get("ears") or {"pointy": "pointy", "round": "round", "round_dark": "round_dark", "big_round": "big_round",
                               "long": "long", "floppy": "floppy", "elephant": "elephant", "round_side": "monkey",
                               "tufts": "none", "antennae": "antennae", "horns": "fin"}.get(sp["ears"], "round")
    if sp.get("ears") not in (None, SPECIES.get(a.key, (0, 0, None))[2]):     # writer asked for a different ear
        e = {"pointy": "pointy", "round": "round", "long": "long", "floppy": "floppy", "big_round": "big_round",
             "none": "none"}.get(sp["ears"], e)
    hy, hrx, hry = a.hy, a.hrx, a.hry
    inner = lighten(INNER_EAR, .1) if sum(m) > 300 else (230, 150, 160)
    if front:
        if e == "floppy":
            for sx in (-1, 1):
                p = _bez([(sx * hrx * .55, hy - hry * .75), (sx * (hrx + 4), hy - hry * .6), (sx * (hrx + 3.5), hy + hry * .45)], 12)
                k.part(k.tube(p, [3.5, 6.0, 6.2, 4.6]), darken(m, .22), shade=(.25, .3))
        return
    if e in ("pointy", "fox", "cat", "small_pointy", "pointy_tall", "squirrel"):
        tall = {"pointy": 1.0, "fox": 1.1, "cat": .72, "small_pointy": .62, "pointy_tall": 1.2, "squirrel": .7}[e]
        spread = {"cat": .95, "small_pointy": .8}.get(e, 1.0)
        for sx in (-1, 1):
            bi, bo = (sx * hrx * .25 * spread, hy - hry * .5), (sx * hrx * .95 * spread, hy - hry * .2)
            tip = (sx * hrx * .88 * spread, hy - hry - 13 * tall)
            ear = _bez([bi, (sx * hrx * .4 * spread, hy - hry - 4 * tall), tip], 10) + \
                _bez([tip, (sx * hrx * 1.12 * spread, hy - hry - 2 * tall), bo], 10)[1:]
            k.part(k.poly(ear), m, shade=(.28, .4))
            mid = ((bi[0] + bo[0]) / 2, (bi[1] + bo[1]) / 2)
            in_tip = (tip[0] * .92 + mid[0] * .08, tip[1] * .85 + mid[1] * .15)
            inner_pts = _bez([(mid[0] - sx * 4.5, mid[1]), (mid[0] - sx * 3, (mid[1] + in_tip[1]) / 2), in_tip], 8) + \
                _bez([in_tip, (mid[0] + sx * 3.8, (mid[1] + in_tip[1]) / 2), (mid[0] + sx * 4.5, mid[1] + 1)], 8)[1:]
            k.fill(k.poly(inner_pts), (255, 225, 205) if e == "fox" else inner)
            if e == "fox":
                tsh = k.poly([tip, (tip[0] - sx * 3.0, tip[1] + 8 * tall), (tip[0] + sx * 3.6, tip[1] + 7.5 * tall)])
                k.part(tsh, (95, 60, 70), k.li * .8)
            if e == "squirrel":
                k.part(k.tube(_bez([tip, (tip[0] + sx * 1.5, tip[1] - 3), (tip[0] + sx * .5, tip[1] - 5)], 6), [1.8, 1.1, .2]), m, k.li)
    elif e in ("round", "round_dark", "big_round", "monkey"):
        r = {"round": 6.5, "round_dark": 6.5, "big_round": 11.5, "monkey": 6.0}[e]
        col = (55, 52, 62) if e == "round_dark" else m
        for sx in (-1, 1):
            if e == "monkey":
                x, y = sx * (hrx + 1.5), hy + 1
            else:
                ang = math.radians(-90 + sx * (52 if e != "big_round" else 48))
                x, y = math.cos(ang) * hrx * .95, hy + math.sin(ang) * hry * .95
            k.part(k.E(x, y, r, r * .95), col, shade=(.28, .4))
            k.fill(k.E(x + (0 if e != "monkey" else -sx * .8), y + .6, r * .55, r * .52),
                   (95, 90, 100) if e == "round_dark" else (a.b if e == "monkey" else inner))
    elif e in ("long", "donkey"):
        perk = 1.0
        if base.MOUTH.get(a.sp.get("_emo", "happy"), (0,))[0] < 0:
            perk = .6
        for sx in (-1, 1):
            tip = (sx * (9 + (1 - perk) * 20), hy - hry - 19 * perk + (1 - perk) * 14)
            p = _bez([(sx * 6.5, hy - hry + 3), (sx * 10, hy - hry - 8 * perk), tip], 12)
            r0 = 6.0 if e == "long" else 6.8
            k.part(k.tube(p, [3.4, r0, r0 * .9, 3.4]), m, shade=(.28, .4))
            k.fill(k.tube(p[2:-1], [1.3, r0 * .5, r0 * .48, 1.5]), inner)
            if e == "donkey" or a.look.get("ear_tips"):
                k.clip_paste(k.tube(p, [3.4, r0, r0 * .9, 3.4]), k.E(tip[0], tip[1], 5, 4.5), darken(m, .55))
    elif e in ("side", "side_big"):
        big = 1.35 if e == "side_big" else 1.0
        for sx in (-1, 1):
            x, y = sx * (hrx + 3.5 * big), hy - hry * .45
            k.part(k.rot_ell(x, y, 6.2 * big, 3.0 * big, sx * 18), m, shade=(.28, .4))
            k.fill(k.rot_ell(x + sx * .5, y + .3, 4.2 * big, 1.6 * big, sx * 18), inner)
    elif e == "pig":
        for sx in (-1, 1):
            base_i, base_o = (sx * hrx * .3, hy - hry * .75), (sx * hrx * .9, hy - hry * .35)
            tip = (sx * (hrx + 3), hy - hry - 4)
            k.part(k.poly(_bez([base_i, (sx * hrx * .6, hy - hry - 4), tip], 8) + _bez([tip, (sx * hrx * 1.05, hy - hry * .5), base_o], 8)[1:]),
                   darken(m, .06), shade=(.28, .4))
    elif e == "elephant":
        for sx in (-1, 1):
            sh = k.blob(sx * (hrx + 5), hy + 2, 11.5, 14, [(90, 40, .1)])
            k.part(sh, m, shade=(.28, .4))
            k.fill(k.blob(sx * (hrx + 5.6), hy + 2.5, 8, 10.5, [(90, 40, .1)]), (240, 185, 200))
            k.form(sh, .2, 0)
    elif e == "fin":
        for sx in (-1, 1):
            tip = (sx * (hrx + 7), hy - 6)
            k.part(k.poly(_bez([(sx * hrx * .8, hy - hry * .55), (sx * (hrx + 3), hy - 11), tip], 8) +
                          _bez([tip, (sx * (hrx + 2), hy - 3), (sx * hrx * .95, hy + 1)], 8)[1:]), a.acc, shade=(.25, .35))
            for j in (0.35, .7):
                p0 = (sx * hrx * .85, hy - hry * .3 + j * 4)
                k.stroke([p0, (p0[0] * .45 + tip[0] * .55, p0[1] * .45 + tip[1] * .55)], .9, darken(a.acc, .3), (.3, 1, .2))
    elif e == "antennae":
        for sx in (-1, 1):
            p = _bez([(sx * 5, hy - hry + 2), (sx * 7, hy - hry - 9), (sx * 13, hy - hry - 12)], 10)
            k.part(k.tube(p, [1.1, 1.0, .9]), darken(a.m, .4), k.li)
            k.part(k.E(p[-1][0], p[-1][1], 2.8, 2.8), a.acc if a.key != "bee" else (60, 50, 60), shade=(.25, .4))


def _horns(a: _A):
    k, hy, hrx, hry = a.k, a.hy, a.hrx, a.hry
    h = a.look.get("horns") or ("cow" if "horns" in a.ex else None)
    cream = (250, 235, 200)
    if h == "cow":
        for sx in (-1, 1):
            p = _bez([(sx * hrx * .55, hy - hry * .8), (sx * (hrx * .9), hy - hry - 2), (sx * (hrx * .8), hy - hry - 7)], 10)
            k.part(k.tube(p, [2.6, 2.0, .9]), cream, shade=(.2, .35))
    elif h == "goat":
        for sx in (-1, 1):
            p = _bez([(sx * hrx * .3, hy - hry * .85), (sx * hrx * .45, hy - hry - 10), (sx * hrx * 1.1, hy - hry - 6), (sx * hrx * .95, hy - hry + 2)], 14)
            k.part(k.tube(p, [3.0, 2.4, 1.6, .8]), (215, 195, 165), shade=(.2, .35))
            for t in (3, 6, 9):
                q = p[t]
                k.stroke([(q[0] - 1.6, q[1]), (q[0] + 1.6, q[1] + .5)], .7, darken((215, 195, 165), .25), (1, 1, 1))
    elif h == "ossicone":
        for sx in (-1, 1):
            p = [(sx * 4.5, hy - hry + 2), (sx * 6, hy - hry - 7)]
            k.part(k.tube(p, [1.6, 1.4]), darken(a.m, .1))
            k.part(k.E(p[-1][0], p[-1][1], 2.6, 2.4), (150, 100, 70), shade=(.25, .35))
    elif h == "dragon":
        for sx in (-1, 1):
            p = _bez([(sx * hrx * .4, hy - hry * .8), (sx * hrx * .55, hy - hry - 5), (sx * hrx * .9, hy - hry - 9)], 10)
            k.part(k.tube(p, [2.8, 2.0, .6]), cream, shade=(.2, .35))
    elif "horns" in a.ex:
        for sx in (-1, 1):
            p = _bez([(sx * hrx * .5, hy - hry * .8), (sx * hrx * .7, hy - hry - 5)], 6)
            k.part(k.tube(p, [2.4, .8]), cream)


def _mane_back(a: _A):
    k, hy, hrx, hry = a.k, a.hy, a.hrx, a.hry
    mt = a.look.get("mane") or ("lion" if "mane" in a.ex and a.key not in LOOK else None)
    if mt == "lion":
        col = darken(a.m, .3) if a.key == "lion" else darken(a.m, .3)
        col = (205, 120, 55) if a.key == "lion" else col
        outer = k.scallop(0, hy + 1, hrx * 1.5, hry * 1.5, 13, .16)
        k.part(outer, col, shade=(.3, .35))
        k.fill(k.scallop(0, hy + 1, hrx * 1.28, hry * 1.28, 13, .14, phase=.25), lighten(col, .15))
    elif mt in ("horse", "zebra", "rainbow", "short"):
        cols = {"horse": [darken(a.m, .45)], "zebra": [(55, 50, 60), (250, 250, 250)], "short": [darken(a.m, .35)],
                "rainbow": [(255, 150, 200), (190, 150, 255), (130, 200, 255), (255, 210, 120)]}[mt]
        n = 6 if mt != "short" else 4
        for i in range(n):                                    # crest ridge running over the head
            t = i / (n - 1)
            ang = math.radians(-150 + t * 95)
            x, y = math.cos(ang) * hrx * .98, hy + math.sin(ang) * hry * .98
            k.part(k.rot_ell(x, y - 1.5, 4.0, 5.8, math.degrees(ang) + 90), cols[i % len(cols)], shade=(.25, .35))


def _mane_front(a: _A):
    k, hy, hry = a.k, a.hy, a.hry
    mt = a.look.get("mane")
    if mt in ("horse", "zebra", "rainbow"):
        cols = {"horse": [darken(a.m, .45)], "zebra": [(55, 50, 60)],
                "rainbow": [(255, 150, 200), (190, 150, 255), (130, 200, 255)]}[mt]
        for j, (dx, ang) in enumerate(((-3.5, -20), (0, 8), (3.4, 30))):    # forelock
            p = _bez([(dx * .4, hy - hry + 1), (dx + 1, hy - hry + 5), (dx * 1.4 - 1, hy - hry + 9.5)], 8)
            k.part(k.tube(p, [3.2, 2.6, .6]), cols[j % len(cols)], k.li * 1.2, (.2, .3))
    elif mt == "lion":
        for dx in (-2.4, 0, 2.4):
            p = _bez([(dx, hy - hry + .5), (dx * 1.6, hy - hry + 3.5), (dx * 2, hy - hry + 6.5)], 6)
            k.part(k.tube(p, [2.0, 1.5, .3]), (205, 120, 55), k.li, (.2, .3))


def _tail(a: _A, bx=0, by=80):
    k, m = a.k, a.m
    t = a.look.get("tail") or {"bushy": "bushy", "thin": "cat", "curly": "curly", "thick": "thick", "fish": "none",
                               "none": "none"}.get(a.sp["tail"], "none")
    if a.sp.get("tail") not in (None, SPECIES.get(a.key, (0,) * 5)[4]):
        t = {"bushy": "bushy", "thin": "cat", "curly": "curly", "thick": "thick", "none": "none"}.get(a.sp["tail"], t)
    if t in ("fox", "bushy"):
        path = _bez([(9, by + 6), (28, by + 12), (38, by - 10), (30, by - 28)], 18)
        tsh = k.tube(path, [3.5, 7.5, 8.6, 7.2, 1.5])
        k.part(tsh, m, shade=(.3, .35))
        tip = path[12:]
        tcol = a.b if t == "fox" else lighten(m, .45)
        k.part(k.tube(tip, [7.0, 6.0, 3.6, 1.5]), tcol, k.li)
        k.form(k.tube(tip, [7.0, 6.0, 3.6, 1.5]), .25, 0)
    elif t == "squirrel":
        path = _bez([(8, by + 8), (34, by + 6), (36, by - 34), (16, by - 40)], 22)
        sh = k.tube(path, [3.5, 9, 10.5, 10, 6])
        k.part(sh, m, shade=(.3, .35))
        for i in range(4, 20, 4):
            q = path[i]
            k.stroke(_bez([(q[0] - 3, q[1] - 1), (q[0], q[1] + 1.5), (q[0] + 3, q[1] - 1)], 6), 1.0, darken(m, .2), (.2, 1, .2))
    elif t in ("cat", "striped", "mouse", "monkey", "tuft", "wag"):
        if t == "monkey":
            path = _bez([(10, by + 4), (30, by + 8), (34, by - 14), (24, by - 16), (22, by - 8)], 20)
        elif t == "wag":
            path = _bez([(11, by + 2), (22, by + 2), (26, by - 12)], 14)
        elif t == "mouse":
            path = _bez([(10, by + 6), (32, by + 14), (40, by - 4), (34, by - 12)], 18)
        else:
            path = _bez([(10, by + 5), (30, by + 10), (34, by - 10), (28, by - 16)], 18)
        r = {"wag": 2.8, "mouse": 1.3}.get(t, 2.0)
        sh = k.tube(path, [r * 1.3, r, r * .9])
        k.part(sh, m, shade=(.25, .3))
        if t == "striped":
            for i in range(4, 18, 4):
                k.clip_paste(sh, k.E(path[i][0], path[i][1], 1.2, 3.0), (60, 45, 55))
        if t == "cat":
            k.clip_paste(sh, k.E(path[-1][0], path[-1][1], 3.2, 3.2), lighten(m, .5))
        if t == "tuft":
            end = path[-1]
            k.part(k.rot_ell(end[0], end[1] - 2.5, 2.6, 4.2, 20), darken(m, .35) if a.key != "lion" else (205, 120, 55), shade=(.2, .3))
    elif t in ("hair", "rainbow"):
        cols = [darken(m, .45)] if t == "hair" else [(255, 150, 200), (190, 150, 255), (130, 200, 255)]
        for j, off in enumerate((-3, 0, 3)):
            path = _bez([(10, by), (24 + off, by - 4), (30 + off, by + 8), (26 + off * 1.5, by + 16)], 14)
            k.part(k.tube(path, [2.4, 3.4, 2.6, .6]), cols[j % len(cols)], shade=(.2, .3))
    elif t == "curly":
        pts = [(15 + math.cos(a_) * (3.2 - a_ * .25), by + math.sin(a_) * (3.2 - a_ * .25)) for a_ in [i * .35 for i in range(22)]]
        k.part(k.tube(pts, [1.3, 1.1]), darken(m, .05), k.li)
    elif t == "puff":
        k.part(k.scallop(13.5, by + 4, 5.0, 4.6, 8, .15), lighten(m, .6), shade=(.25, .3))
    elif t in ("thick", "dragon"):
        path = _bez([(10, by), (30, by + 12), (42, by + 4), (44, by - 10)], 18)
        sh = k.tube(path, [8, 6.0, 3.6, 1.4])
        if t == "dragon":
            end = path[-1]
            k.part(k.poly([(end[0] - 4.5, end[1] + 1), (end[0], end[1] - 6.5), (end[0] + 4.5, end[1] + 1), (end[0], end[1] + 3)]),
                   a.acc, shade=(.25, .3))
        k.part(sh, m, shade=(.3, .35))
        if t == "thick":
            for i in (6, 10, 14):
                q = path[i]
                k.part(k.E(q[0], q[1] - 4.5 + i * .18, 1.6, 1.2), darken(m, .12), k.li * .7)


def _body(a: _A):
    """Legs, body, belly, patterns. Returns the body shape (for the head's contact shadow)."""
    k, m, b = a.k, a.m, a.b
    chubby, slim = a.build == "chubby", a.build == "slim"
    bw = 19.5 if chubby else (13.5 if slim else 15.5)
    bh = 17.5 if chubby else 16
    by = 77 if not chubby else 76
    feet = a.look.get("feet", "paw")
    limb = a.limbs
    if a.look.get("hump"):
        k.part(k.E(4, by - 15, 11, 9), a.m, shade=(.3, .35))
    lx = bw * .52
    for sx in (-1, 1):
        k.part(k.egg(sx * lx, 90, 5.6 if not chubby else 6.6, 6.6, top=.95), limb)
        if feet == "hoof":
            k.part(k.blob(sx * lx, 94.5, 5.6, 4.0, [(90, 60, .1)]), HOOF, shade=(.25, .35))
            k.stroke([(sx * lx, 92.5), (sx * lx, 97)], .8, darken(HOOF, .4), (1, 1, 1))
        else:
            fw = 9.5 if a.look.get("big_feet") else 7.4
            fcol = (120, 70, 60) if feet == "sock" else (darken(limb, .06) if limb != a.m else darken(m, .06))
            k.part(k.egg(sx * (lx + .5), 95.2, fw, 4.1, top=1.05), fcol, shade=(.25, .35))
            if feet != "sock" and limb == a.m:
                k.fill(k.E(sx * (lx + .5), 95.8, fw * .45, 2.0), lighten(b, .2))
    bsh = k.egg(0, by, bw, bh, top=.78)
    k.part(bsh, m)
    if limb != a.m:   # panda: dark shoulders band
        k.clip_paste(bsh, k.E(0, by - bh * .75, bw * 1.2, bh * .45), limb)
    bel = k.egg(0, by + 3.5, bw * .58, bh * .62, top=.85)
    k.fill(bel, b)
    if a.look.get("pouch"):
        k.stroke(_bez([(-bw * .45, by + 3), (0, by + 9), (bw * .45, by + 3)], 10), 1.2, darken(b, .25), (.3, 1, .3))
    if a.look.get("plates"):
        for yy in range(int(by - 6), int(by + 13), 5):
            hw = bw * .58 * math.sqrt(max(0, 1 - ((yy - by - 3.5) / (bh * .62)) ** 2)) * .85
            k.stroke(_bez([(-hw, yy - .8), (0, yy + 1.2), (hw, yy - .8)], 10), .9, darken(b, .18), (.3, 1, .3))
    _pattern(a, bsh, 0, by, bw, bh)
    k.form(bsh, .32, .45)
    return bsh


def _pattern(a: _A, clip, cx, cy, rx, ry, head=False):
    k = a.k
    if "stripes" in a.ex and a.key in ("tiger", "zebra", "bee") or ("stripes" in a.ex and a.key not in LOOK):
        col = (60, 45, 55)
        if head:
            for dx in (-3.5, 0, 3.5):                     # forehead stripes
                k.clip_paste(clip, k.poly([(cx + dx - 1.1, cy - ry - 1), (cx + dx + 1.1, cy - ry - 1), (cx + dx * 1.1, cy - ry * .55)]), col)
            for sx in (-1, 1):
                for j in (0, 1):
                    yy = cy + j * 4.5 - 2
                    k.clip_paste(clip, k.poly([(cx + sx * (rx + 1), yy - 1.4), (cx + sx * (rx + 1), yy + 1.4), (cx + sx * rx * .62, yy + .3)]), col)
        else:
            for sx in (-1, 1):
                for j in range(3):
                    yy = cy - ry * .45 + j * ry * .42
                    k.clip_paste(clip, k.poly([(cx + sx * (rx + 1), yy - 1.8), (cx + sx * (rx + 1), yy + 1.8), (cx + sx * rx * .45, yy + .6)]), col)
    if "spots" in a.ex:
        col = (60, 55, 65) if a.key == "cow" else (darken(a.m, .3) if a.key != "giraffe" else (190, 120, 60))
        spots = ((-.55, -.35, .32), (.5, -.1, .26), (-.2, .45, .2), (.62, .5, .22)) if not head else ((-.6, -.55, .22), (.65, -.45, .16))
        for fx, fy, r in spots:
            sh = k.blob(cx + fx * rx, cy + fy * ry, r * rx, r * rx * .85, [(30, 50, .12), (200, 40, -.1)])
            k.clip_paste(clip, sh, col)
    if "scales" in a.ex and not head:
        for fx, fy in ((-.6, -.4), (.55, -.2), (-.45, .3), (.6, .4)):
            k.clip_paste(clip, k.E(cx + fx * rx, cy + fy * ry, 1.4, 1.1), darken(a.m, .14))


def _muzzle(a: _A, mouth_, eyes, emo):
    """Muzzle, nose and mouth. Called after the head is filled (before head lighting)."""
    k, m, b, hy = a.k, a.m, a.b, a.hy
    mz = a.look.get("muzzle") or {"muzzle": "bear", "flat": "cat", "snout": "pig", "trunk": "trunk", "beak": "cat",
                                  "duck_bill": "cat", "long_snout": "dragon"}.get(a.sp["face"], "cat")
    my = hy + 9.0
    if mz == "fox":
        for sx in (-1, 1):
            k.fill(k.blob(sx * 7.3, hy + 9, 9.4, 6.8, [(90 + sx * 60, 30, .15)]), b)
        k.fill(k.E(0, hy + 11.5, 7.2, 6.2), b)
        return ("nose", 0, hy + 7.2, 2.4, hy + 12.5, 4.8)
    if mz in ("bear", "dog", "long"):
        w = {"bear": 8.0, "dog": 8.4, "long": 7.2}[mz]
        h = {"bear": 6.0, "dog": 6.4, "long": 6.4}[mz]
        k.fill(k.egg(0, my, w, h, top=.9), b)
        return ("nose", 0, my - h * .45, 2.9 if mz != "long" else 2.6, my + h * .3, 4.6)
    if mz == "cat":
        for sx in (-1, 1):
            k.fill(k.E(sx * 2.9, my - .2, 4.0, 3.1), b)
        return ("nose_s", 0, my - 3.0, 1.9, my + 1.6, 4.0)
    if mz == "bunny":
        for sx in (-1, 1):
            k.fill(k.E(sx * 2.9, my - .6, 4.0, 3.1), lighten(b, .3))
        return ("bunny", 0, my - 3.4, 2.0, my + 1.0, 4.2)
    if mz == "mouse":
        k.fill(k.egg(0, my - 1, 6.0, 4.6, top=.8), b)
        return ("mouse", 0, my - 3.0, 2.0, my + 1.6, 3.8)
    if mz == "pig":
        sn = k.E(0, my - 1.2, 6.2, 4.4)
        k.part(sn, darken(m, .08), k.li, (.2, .4))
        for sx in (-1, 1):
            k.fill(k.E(sx * 2.0, my - 1.2, 1.1, 1.7), darken(m, .45))
        return ("none", 0, 0, 0, my + 5.2, 4.2)
    if mz == "cow":
        sn = k.egg(0, my + .5, 10.5, 6.6, top=1.05)
        k.part(sn, (255, 195, 205), k.li, (.2, .4))
        for sx in (-1, 1):
            k.fill(k.E(sx * 3.6, my - .6, 1.3, 1.8), (175, 100, 115))
        return ("none", 0, 0, 0, my + 3.6, 5.2)
    if mz == "horse":
        sn = k.egg(0, my + 1.5, 10.5, 7.0, top=1.05)
        k.part(sn, b, k.li, (.15, .3))
        for sx in (-1, 1):
            k.fill(k.E(sx * 3.4, my - .5, 1.1, 1.6), darken(b, .45))
        return ("none", 0, 0, 0, my + 4.4, 4.6)
    if mz == "sheep":
        return ("nose_s", 0, my - 2.6, 1.9, my + 2.0, 4.0)
    if mz == "monkey":
        for sx in (-1, 1):
            k.fill(k.E(sx * 7, hy - 1.5, 8.5, 8.5), b)
        k.fill(k.egg(0, my + .5, 11, 7.5, top=.9), b)
        return ("dots", 0, my - 2.2, 1.0, my + 2.8, 5.0)
    if mz == "dragon":
        sn = k.egg(0, my + .5, 11, 6.4, top=1.05)
        k.part(sn, lighten(m, .25), k.li, (.15, .35))
        for sx in (-1, 1):
            k.fill(k.E(sx * 3.4, my - 1.6, 1.2, .8), darken(m, .5))
        return ("none", 0, 0, 0, my + 3.0, 6.0)
    if mz == "trunk":
        return ("trunk", 0, my, 0, my + 3, 3.4)
    return ("nose_s", 0, my - 2.6, 1.8, my + 1.8, 4.0)


def _face(a: _A, mouth_, eyes, emo, plan):
    k, hy = a.k, a.hy
    kind, nx, ny, nw, mouth_y, mw = plan
    a_iris = _iris(a.m)
    lash = str(a.sp.get("gender", "")).lower().startswith("f")
    look = (0, .2) if a.look.get("sleepy_lids") else (0, 0)
    for sx in (-1, 1):
        eye(a.k, sx * 8.6, a.ey, 7.0, sx, eyes, emo, iris=a_iris, lash=lash, brow_col=_brow_col(a.m), look_extra=look)
    k.blush(-15.5, hy + 7.5, 3.8, 2.4)
    k.blush(15.5, hy + 7.5, 3.8, 2.4)
    if kind == "trunk":
        tr = _bez([(0, hy + 2), (0, hy + 12), (-1, hy + 18), (5, hy + 21)], 16)
        sh = k.tube(tr, [4.2, 3.6, 2.8, 2.6])
        draw_mouth(k, -7.5, hy + 12.5, 3.2, mouth_, emo)
        k.part(sh, a.m, shade=(.25, .35))
        for i in (5, 8, 11):
            q = tr[i]
            k.stroke([(q[0] - 2.4, q[1]), (q[0] + 2.4, q[1] + .3)], .7, darken(a.m, .2), (.3, 1, .3))
        return
    if kind in ("nose", "nose_s", "mouse"):
        nose(k, nx, ny, nw, NOSE if kind != "mouse" else (240, 130, 150))
        k.stroke([(nx, ny + nw * .6), (nx, mouth_y - .6)], .8, OUT, (1, 1, 1))
    elif kind == "bunny":
        nose(k, nx, ny, nw, (240, 120, 150))
        k.stroke([(nx, ny + nw * .6), (nx, mouth_y - .4)], .8, OUT, (1, 1, 1))
    elif kind == "dots":
        for sx in (-1, 1):
            k.fill(k.E(sx * 1.4, ny, nw, nw * .7), darken(a.b, .5))
    tongue = a.look.get("muzzle") == "dog" and mouth_ == 2 and MOUTH[emo][0] > .3
    draw_mouth(k, 0, mouth_y, mw, mouth_, emo, buck=kind == "bunny", teeth=a.look.get("muzzle") == "dragon")
    if tongue:
        k.part(k.egg(0, mouth_y + mw * 1.25, mw * .45, mw * .55, top=1.1), TONGUE, k.li)
        k.stroke([(0, mouth_y + mw * .9), (0, mouth_y + mw * 1.5)], .6, darken(TONGUE, .3), (1, 1, 1))
    if "whiskers" in a.ex:
        for sx in (-1, 1):
            for j, dy in enumerate((-1.2, 1.0)):
                x0, y0 = sx * 7.5, ny + 2 + dy
                k.stroke([(x0, y0), (x0 + sx * 7, y0 + dy * .9 - .8)], .55, darken(a.m, .5), (1, .8, .2))


def _head(a: _A, bsh, mouth_, eyes, emo, arms):
    k, m, hy, hrx, hry = a.k, a.m, a.hy, a.hrx, a.hry
    if a.look.get("neck"):
        neck = k.tube([(0, 66), (0, hy + 6)], [6.2, 5.4])
        k.part(neck, m)
        _pattern(a, neck, 0, 50, 6, 14)
        k.form(neck, .3, .4)
    _mane_back(a)
    if a.look.get("wool"):
        k.part(k.scallop(0, hy - 2, hrx * 1.22, hry * 1.12, 11, .2), (255, 255, 255), shade=(.25, .35))
    _horns(a)
    if a.look.get("antlers"):
        for sx in (-1, 1):
            br = (150, 105, 65)
            main = _bez([(sx * 6, hy - hry + 3), (sx * 9, hy - hry - 6), (sx * 16, hy - hry - 10)], 10)
            k.part(k.tube(main, [1.6, 1.3, .9]), br)
            for t in (4, 7):
                q = main[t]
                k.part(k.tube([q, (q[0] + sx * .5, q[1] - 5)], [1.1, .7]), br)
    _ears(a)
    ruff = [(150, 18, .12), (30, 18, .12)] if a.look.get("ruff") else None
    head = k.blob(0, hy, hrx, hry, ruff) if ruff else k.egg(0, hy, hrx, hry, top=.92, bot=1.04)
    if bsh is not None:
        k.occlude(bsh, head, 3.2)
    k.part(head, m)
    if a.look.get("forehead") or "stripes" in a.ex:
        _pattern(a, head, 0, hy, hrx, hry, head=True)
    if "spots" in a.ex and a.key in ("cow", "giraffe"):
        _pattern(a, head, 0, hy, hrx, hry, head=True)
    if a.look.get("patch"):
        k.clip_paste(head, k.blob(8.6, a.ey - 1, 7.5, 7, [(0, 40, .15)]), darken(m, .25))
    if "panda" in a.ex:
        for sx in (-1, 1):
            k.fill(k.rot_ell(sx * 8.8, a.ey + .6, 6.6, 8.6, sx * -28), (55, 52, 62))
    if a.look.get("brow_mark"):
        for sx in (-1, 1):
            k.fill(k.E(sx * 7.5, a.ey - 9.5, 3.0, 1.6), lighten(m, .45))
    plan = _muzzle(a, mouth_, eyes, emo)
    k.form(head, .3, .5, .18)
    _mane_front(a)
    if a.look.get("wool"):
        k.part(k.scallop(0, hy - hry * .95, hrx * .62, 4.2, 7, .3), (255, 255, 255), k.li, (.2, .3))
    _ears(a, front=True)
    _face(a, mouth_, eyes, emo, plan)
    if a.look.get("beard"):
        k.part(k.poly(_bez([(-3, hy + 15), (0, hy + 24), (3, hy + 15)], 8)), lighten(m, .3), k.li, (.2, .3))
    if "unicorn_horn" in a.ex:
        top = hy - hry - 13
        k.part(k.poly([(-2.8, hy - hry + 2.5), (0, top), (2.8, hy - hry + 2.5)]), (255, 215, 110), shade=(.25, .45))
        for j in range(3):
            yy = hy - hry + 1 - j * 4
            w_ = 2.6 * (yy - top) / (hy - hry + 2.5 - top)
            k.stroke([(-w_, yy + .6), (w_, yy - .8)], .7, (225, 160, 60), (1, 1, 1))
    return head


def _mammal(k, sp, mouth_, eyes, emo, arms):
    a = _A(k, sp)
    sp["_emo"] = emo
    if a.look.get("wings") == "bat" or ("wings" in a.ex and a.key not in LOOK):
        _bat_wings(a, arms)
    _tail(a)
    bsh = _body(a)
    chubby = a.build == "chubby"
    sh_x, sh_y = (16.5, 64.5) if chubby else (12, 67)
    L, r = (12, 3.8) if chubby else (12, 3.3)
    hand = (120, 70, 60) if a.look.get("feet") == "sock" else (HOOF if a.look.get("feet") == "hoof" else a.limbs)
    two_arms(k, arms, (sh_x, sh_y), L, r, a.limbs, "paw", hand_col=hand, clap_x=3.2, layer="low")
    _head(a, bsh, mouth_, eyes, emo, arms)
    two_arms(k, arms, (sh_x, sh_y), L + 1.5, r, a.limbs, "paw", hand_col=hand, layer="high")
    _outfit_animal(a)


def _bat_wings(a, arms):
    k = a.k
    flap = -6 if arms in ("up", "wave") else 0
    for sx in (-1, 1):
        root = (sx * 9, 62)
        tip = (sx * 48, 30 + flap)
        pts = [root, (sx * 26, 38 + flap * .5), tip]
        lower = []
        for j in range(3):                                  # scalloped trailing edge
            p0 = (tip[0] * (1 - j / 3) + sx * 12 * (j / 3), tip[1] * (1 - j / 3) + 70 * (j / 3))
            p1 = (tip[0] * (1 - (j + 1) / 3) + sx * 12 * ((j + 1) / 3), tip[1] * (1 - (j + 1) / 3) + 70 * ((j + 1) / 3))
            mid = ((p0[0] + p1[0]) / 2 - sx * 3.5, (p0[1] + p1[1]) / 2 - 2)
            lower += _bez([p0, mid, p1], 6)[1:]
        sh = k.poly(_bez(pts, 10) + lower)
        k.part(sh, darken(a.m, .12), shade=(.25, .3))
        k.glaze(sh, a.acc, .25)
        for j in (1, 2):
            p1 = (tip[0] * (1 - j / 3) + sx * 12 * (j / 3), tip[1] * (1 - j / 3) + 70 * (j / 3))
            k.stroke([(sx * 24, 40 + flap * .5), p1], .9, darken(a.m, .35), (.3, 1, .3))


def _outfit_animal(a):
    _accessory(a.k, a.sp, a.hy, a.hry, 77, kind="animal")


# ---------------------------------------------------------------- other body plans
def _bird(k, sp, mouth_, eyes, emo, arms):
    a = _A(k, sp)
    m, b, acc = a.m, a.b, a.acc
    lk = a.look
    a.hy = 44
    if lk.get("fan"):                                   # peacock fan tail
        for i in range(9):
            ang = math.radians(-165 + i * 18.75)
            x, y = math.cos(ang) * 40, 66 + math.sin(ang) * 46
            p = _bez([(0, 70), (x * .5, 70 + (y - 70) * .55), (x, y)], 8)
            k.part(k.tube(p, [1.5, 4.5, 7.5]), (60, 170, 140), k.li, (.2, .3))
            k.fill(k.E(x, y, 4.4, 4.6), (90, 200, 170))
            k.part(k.E(x, y + .4, 2.8, 3.1), (40, 110, 200), k.li * .7)
            k.fill(k.E(x, y + .8, 1.4, 1.5), (60, 45, 90))
    if lk.get("tail_feathers"):
        cols = [(60, 150, 110), (40, 90, 160), (230, 90, 60)] if lk["tail_feathers"] == "rooster" else [lighten(m, .1), darken(m, .1)]
        for j, ang in enumerate((-60, -35, -10)):
            a_ = math.radians(ang)
            p = _bez([(14, 70), (14 + math.cos(a_) * 14, 70 + math.sin(a_) * 20 - 6), (16 + math.cos(a_) * 24, 70 + math.sin(a_) * 26)], 10)
            k.part(k.tube(p, [2.5, 4.0, 1.2]), cols[j % len(cols)], shade=(.2, .3))
    if lk.get("tufts"):
        for sx in (-1, 1):
            p = _bez([(sx * 11, 31), (sx * 17, 22), (sx * 23, 15)], 10)
            k.part(k.tube(p, [3.5, 4.4, 3.2, .6]), m, shade=(.2, .3))
    crest = lk.get("crest")
    if crest in ("songbird", "crow", "duck"):
        for j, (dx, h) in enumerate(((-2.5, 8), (1, 10), (4.5, 7))):
            p = _bez([(dx, 28), (dx + 1, 28 - h * .6), (dx + 3, 28 - h)], 8)
            k.part(k.tube(p, [2.0, 1.4, .3]), m if crest != "songbird" else (lighten(acc, .1) if j == 1 else m), shade=(.2, .3))
    if crest == "peacock":
        for dx in (-3.5, 0, 3.5):
            k.part(k.tube([(dx * .3, 26), (dx, 15)], [.7, .6]), (40, 90, 160), k.li * .7)
            k.part(k.E(dx, 14, 1.9, 1.9), (60, 170, 200), k.li * .8)
    if lk.get("comb"):
        big = lk["comb"] == "big"
        k.group([k.E(dx, 24.5 - (2.5 if dx == 0 else 0) * (1.4 if big else 1), 2.6 * (1.3 if big else 1), 3.4 * (1.3 if big else 1))
                 for dx in (-3.4, 0, 3.4)], (235, 60, 65), shade=(.25, .35))
    for sx in (-1, 1):
        k.group([k.E(sx * 8 + dx, 96, 2.6, 2.6) for dx in (-3, 0, 3)], (255, 160, 50), shade=(.25, .3))
    bsh = k.egg(0, 60, 27, 35, top=.82)
    k.part(bsh, m)
    if lk.get("mask"):
        for sh in [k.E(sx * 9.8, 47, 12, 12) for sx in (-1, 1)] + [k.E(0, 55, 12, 8)]:
            k.fill(sh, b)
    k.fill(k.egg(0, 76, 18, 17.5, top=.88), b)
    for row in range(3):
        yy = 69 + row * 5.4
        for j in range(-2 + row % 2, 3):
            xx = j * 5.2 + (row % 2) * 2.6 - 1.3
            if abs(xx) < 14 - row * 1.5:
                k.stroke(_bez([(xx - 2, yy), (xx, yy + 2), (xx + 2, yy)], 6), .85, darken(b, .14), (.2, 1, .2))
    k.form(bsh, .32, .5, .2)
    if lk.get("disc"):
        for sx in (-1, 1):
            k.fill(k.E(sx * 9.8, 44, 11.6, 11), lighten(b, .25))
    wing_col = darken(m, .15)
    two_arms(k, arms, (23.5, 60), 14, 4.8, wing_col, "flipper" if lk.get("flipper") else "wing", clap_x=6.5)
    lash = str(sp.get("gender", "")).lower().startswith("f")
    for sx in (-1, 1):
        eye(k, sx * 9.8, 44, 7.6, sx, eyes, emo, iris=_iris(m) if sum(m) > 250 else (120, 90, 50), lash=lash,
            brow_col=_brow_col(m) if sum(m) > 250 else (170, 170, 190))
    k.blush(-17.5, 53.5, 3.8, 2.4)
    k.blush(17.5, 53.5, 3.8, 2.4)
    bcol = lk.get("beak_col") or (255, 170, 50)
    if lk.get("bill"):
        drop = [0, 2.2, 4.4][mouth_]
        by = 54
        if drop:
            k.part(k.E(0, by + 1 + drop * .45, 5.2, 1.2 + drop * .5), MOUTH_DARK, k.li)
            k.part(k.egg(0, by + 2 + drop, 6.0, 1.9, top=1.1), darken(bcol, .08), k.li, (.2, .3))
        k.part(k.egg(0, by, 7.2, 3.0, top=1.1), bcol, k.li * 1.1, (.2, .35))
        for sx in (-1, 1):
            k.fill(k.E(sx * 1.8, by - 1, .6, .4), darken(bcol, .4))
        if mouth_ == 0 and MOUTH[emo][0] > .3:
            k.stroke(_bez([(-5.5, by + 1.2), (0, by + 2.6), (5.5, by + 1.2)], 8), .8, darken(bcol, .5), (.3, 1, .3))
    else:
        drop = [0, 2.2, 4.4][mouth_]
        by = 54
        if drop:
            k.part(k.E(0, by + 1.6 + drop * .4, 2.6, 1.0 + drop * .5), MOUTH_DARK, k.li)
            k.part(k.poly(_bez([(-2.6, by + 1.8 + drop), (0, by + 4.2 + drop), (2.6, by + 1.8 + drop)], 6)), darken(bcol, .1), k.li)
        beak = _bez([(-3.6, by - 1.2), (0, by - 3.2), (3.6, by - 1.2)], 6) + _bez([(3.6, by - 1.2), (.8, by + 3.4), (0, by + 4.6)], 6)[1:] + \
            _bez([(0, by + 4.6), (-.8, by + 3.4), (-3.6, by - 1.2)], 6)[1:]
        k.part(k.poly(beak), bcol, k.li * 1.1, (.22, .3))
        if lk.get("comb"):
            k.part(k.egg(0, by + 6.5, 1.8, 2.6, top=.8), (235, 60, 65), k.li, (.2, .3))
    _accessory(k, sp, a.hy, 18, 76, kind="bird")


def _bug(k, sp, mouth_, eyes, emo, arms):
    a = _A(k, sp)
    m, b, acc = a.m, a.b, a.acc
    bug = a.look.get("bug")
    a.hy = 40
    a.hrx, a.hry = 20.5, 18
    limb = darken(m, .35) if bug != "bee" else (60, 50, 60)
    if bug == "butterfly":
        flap = -5 if arms in ("up", "wave") else 0
        wc1, wc2 = lighten(acc, .1), m
        for sx in (-1, 1):
            up = k.rot_ell(sx * 20, 52 + flap, 17, 13, sx * -30)
            lo = k.rot_ell(sx * 15, 76, 11, 9.5, sx * 25)
            k.part(lo, wc2, shade=(.2, .35))
            k.part(up, wc1, shade=(.2, .35))
            k.part(k.E(sx * 25, 48 + flap, 4.6, 4.6), (255, 255, 255), k.li, (.1, 0))
            k.fill(k.E(sx * 25, 48 + flap, 2.4, 2.4), m)
            k.part(k.E(sx * 17, 78, 3, 3), lighten(acc, .5), k.li)
    if bug in ("bee", "grasshopper"):
        for sx in (-1, 1):
            w = k.rot_ell(sx * 17, 58, 11, 6.5, sx * -35)
            k.glaze(w, (255, 255, 255), .7)
            _outline(k, w, k.li)
            k.stroke([(sx * 9, 62), (sx * 22, 53)], .6, (150, 170, 210), (.3, 1, .3))
    if bug == "grasshopper":
        for sx in (-1, 1):                      # big bent hind legs
            p = [(sx * 10, 80), (sx * 22, 66), (sx * 19, 95)]
            k.part(k.tube(_bez(p, 12), [3.6, 3.0, 1.6]), m, shade=(.25, .35))
    for sx in (-1, 1):
        k.part(k.tube([(sx * 6, 86), (sx * 7, 93)], [1.6, 1.5]), limb)
        k.part(k.egg(sx * 8, 95.3, 5.6, 3.4, top=1.05), limb, shade=(.25, .35))
    if bug == "ant":
        k.part(k.egg(0, 85, 13, 10, top=.85), m, shade=(.3, .4))
        bsh = k.egg(0, 68, 10, 9.5, top=.9)
        k.part(bsh, m, shade=(.3, .45))
    else:
        bw, bh = (16, 18) if bug == "bee" else (11, 16)
        bsh = k.egg(0, 74, bw, bh, top=.8)
        k.part(bsh, m)
        if bug == "bee":
            for yy in (69, 79):
                k.clip_paste(bsh, k.poly(_bez([(-20, yy - 2.2), (0, yy + .8), (20, yy - 2.2)], 8) + _bez([(20, yy + 2.6), (0, yy + 5.6), (-20, yy + 2.6)], 8)), (60, 50, 60))
        else:
            k.fill(k.egg(0, 77, bw * .55, bh * .6), b)
            if bug == "butterfly":
                for yy in (70, 75, 80):
                    k.stroke(_bez([(-5, yy), (0, yy + 1), (5, yy)], 6), .8, darken(b, .2), (.3, 1, .3))
        k.form(bsh, .32, .45)
    two_arms(k, arms, (9.5, 68), 12, 2.2, limb, "paw", hand_col=limb, clap_x=2.6, layer="low")
    _ears(a)
    head = k.egg(0, a.hy, a.hrx, a.hry, top=.95, bot=1.02)
    k.occlude(bsh, head, 3.0)
    k.part(head, m if bug != "bee" else m)
    k.fill(k.E(0, a.hy + 8.5, 9.5, 6.0), lighten(b, .2))
    k.form(head, .3, .5, .18)
    two_arms(k, arms, (9.5, 68), 13, 2.2, limb, "paw", hand_col=limb, layer="high")
    _face(a, mouth_, eyes, emo, ("none", 0, 0, 0, a.hy + 8.5, 4.3))
    _accessory(k, sp, a.hy, a.hry, 74, kind="animal")


def _outline(k, sh, w):
    """Ink outline only (for translucent shapes)."""
    pts = sh[1] if sh[0] == "p" else None
    if pts:
        k.d.line(pts + pts[:1], fill=OUT, width=max(1, int(w * 1.6)), joint="curve")


def _fish(k, sp, mouth_, eyes, emo, arms):
    a = _A(k, sp)
    m, b = a.m, a.b
    whale = a.look.get("whale")
    cy = 58
    rx, ry = (37, 30) if whale else (31, 26)
    if whale:
        tail = _bez([(20, cy + 10), (40, cy + 2), (44, cy - 20)], 12)
        k.part(k.tube(tail, [6, 4.6, 3]), m, shade=(.25, .3))
        k.part(k.poly(_bez([(37, cy - 20), (36, cy - 30), (43, cy - 27)], 6) + _bez([(43, cy - 27), (48, cy - 31), (50, cy - 20)], 6)[1:] +
                      [(44, cy - 17)]), m, shade=(.25, .3))
        for j, (dx, h) in enumerate(((-4, 9), (0, 12), (4, 9))):          # little water spout
            p = _bez([(0, cy - ry + 1), (dx * .4, cy - ry - h * .6), (dx * 1.5, cy - ry - h)], 8)
            k.part(k.tube(p, [1.2, 1.0, .8]), (150, 210, 255), k.li * .8)
            k.part(k.E(p[-1][0], p[-1][1], 2.2, 2.2), (150, 210, 255), k.li * .8, (.1, .5))
    else:
        tail = k.poly(_bez([(rx - 6, cy), (rx + 10, cy - 18), (rx + 16, cy - 16)], 8) + _bez([(rx + 16, cy - 16), (rx + 9, cy), (rx + 16, cy + 16)], 8)[1:] +
                      _bez([(rx + 16, cy + 16), (rx + 10, cy + 18), (rx - 6, cy)], 8)[1:])
        k.part(tail, darken(m, .08), shade=(.25, .35))
        k.part(k.poly(_bez([(-14, cy - ry + 3), (-4, cy - ry - 12), (12, cy - ry - 6), (14, cy - ry + 3)], 12)), darken(m, .08), shade=(.2, .35))
        for j in range(3):
            k.part(k.E(-30 + j * 5, cy - 34 - j * 7, 1.6 + j * .6, 1.6 + j * .6), (200, 235, 255), k.li * .6, (0, .5))
    bsh = k.egg(0, cy, rx, ry, top=.95)
    k.part(bsh, m)
    if whale:
        k.clip_paste(bsh, k.E(0, cy + ry * .85, rx * .85, ry * .6), b)
        for j in range(4):
            k.clip_paste(bsh, k.E(0, cy + ry * .55 + j * 3.2, rx * .5 - j * 2.5, .5), darken(b, .2))
    else:
        k.fill(k.egg(0, cy + 12, rx * .55, ry * .42), b)
        for row in range(2):
            for j in range(-2, 3):
                xx = j * 6 + row * 3
                yy = cy + 4 + row * 5
                if abs(xx) < 20:
                    k.stroke(_bez([(xx - 2.5, yy), (xx, yy + 2.2), (xx + 2.5, yy)], 6), .8, darken(m, .15), (.2, 1, .2))
    k.form(bsh, .3, .5, .2)
    two_arms(k, arms, (rx * .75, cy + 4), 11, 3.4, darken(m, .12), "flipper", clap_x=6)
    a.hy = cy - 6
    for sx in (-1, 1):
        eye(k, sx * 10, cy - 9, 7.6, sx, eyes, emo, iris=_iris(m), brow_col=darken(m, .5))
    k.blush(-18.5, cy + 1, 4, 2.5)
    k.blush(18.5, cy + 1, 4, 2.5)
    draw_mouth(k, 0, cy + 3, 5.4 if not whale else 7, mouth_, emo)
    _accessory(k, sp, cy - 6, ry * .85, cy + 10, kind="animal")


def _snake(k, sp, mouth_, eyes, emo, arms):
    a = _A(k, sp)
    m, b = a.m, a.b
    tail = _bez([(22, 90), (34, 92), (38, 84)], 8)
    k.part(k.tube(tail, [4.2, 2.6, .6]), m, shade=(.25, .3))
    rings = [(0, 89, 27, 7.5), (0, 79.5, 22, 7), (0, 70.5, 17, 6.5)]
    for x, y, rx, ry in rings:
        sh = k.blob(x, y, rx, ry, [(180, 40, -.05)])
        k.part(sh, m)
        k.clip_paste(sh, k.E(0, y + ry * .55, rx * .8, ry * .5), b)
        for fx in (-.6, -.2, .2, .6):
            k.clip_paste(sh, k.poly([(fx * rx - 2, y - ry * .3), (fx * rx, y - ry * .8), (fx * rx + 2, y - ry * .3), (fx * rx, y + ry * .2)]), darken(m, .16))
        k.form(sh, .3, .45)
    neck = k.tube(_bez([(-2, 67), (-4, 60), (0, 52)], 8), [6.2, 5.6, 5.4])
    k.part(neck, m, shade=(.25, .35))
    a.hy = 40
    head = k.egg(0, 40, 19, 15, top=.9, bot=1.08)
    k.part(head, m)
    k.fill(k.egg(0, 47, 12, 6, top=1.0), b)
    k.form(head, .3, .5, .18)
    a.ey = 36
    for sx in (-1, 1):
        eye(k, sx * 8.2, 36, 6.8, sx, eyes, emo, iris=_iris(m), lash=str(sp.get("gender", "")).startswith("f"), brow_col=darken(m, .5))
    k.blush(-14.5, 44, 3.4, 2.2)
    k.blush(14.5, 44, 3.4, 2.2)
    for sx in (-1, 1):
        k.fill(k.E(sx * 2.2, 42.4, .7, .5), darken(m, .5))
    draw_mouth(k, 0, 47.5, 5.2, mouth_, emo)
    _accessory(k, sp, 40, 15, 75, kind="animal")


def _frog(k, sp, mouth_, eyes, emo, arms):
    a = _A(k, sp)
    m, b = a.m, a.b
    for sx in (-1, 1):                                   # bent frog legs + webbed feet
        k.part(k.E(sx * 15, 87, 9, 7.5), m, shade=(.3, .35))
        k.group([k.rot_ell(sx * 15 + dx, 96, 2.4, 3.4, dx * 8) for dx in (-3.5, 0, 3.5)], darken(m, .06), shade=(.2, .3))
    bsh = k.egg(0, 80, 17, 14, top=.85)
    k.part(bsh, m)
    k.fill(k.egg(0, 83, 11, 9.5), b)
    k.form(bsh, .3, .45)
    two_arms(k, arms, (13, 74), 10, 2.8, m, "paw", clap_x=3, layer="low")
    head = k.blob(0, 55, 27, 15, [(270, 30, .05)])
    for sx in (-1, 1):
        k.ink(k.E(sx * 11, 41, 9, 8.6))
    k.ink(head)
    for sx in (-1, 1):
        k.fill(k.E(sx * 11, 41, 9, 8.6), m)
    k.fill(head, m)
    for sx, (dx, dy) in zip((-1, 1, -1), ((-17, 58), (17, 58), (-12, 64))):
        k.fill(k.E(dx, dy, 1.5, 1.2), darken(m, .15))
    k.fill(k.egg(0, 62, 17, 6.5), b)
    k.form(head, .3, .5, .2)
    for sx in (-1, 1):
        k.form(k.E(sx * 11, 41, 9, 8.6), .2, .45)
    two_arms(k, arms, (13, 74), 11, 2.8, m, "paw", layer="high")
    for sx in (-1, 1):
        eye(k, sx * 11, 41, 6.4, sx, eyes, emo, iris=(120, 90, 30), brow_col=darken(m, .5))
    k.blush(-19, 56, 3.6, 2.3)
    k.blush(19, 56, 3.6, 2.3)
    for sx in (-1, 1):
        k.fill(k.E(sx * 2.4, 53, .8, .55), darken(m, .5))
    curve = MOUTH[emo][0]
    if mouth_ == 0 and curve > 0:      # extra-wide frog grin
        k.stroke([(x, 58.5 - curve * 2.4 * (x / 11) ** 2) for x in [-11 + i * 1.375 for i in range(17)]], 1.3, OUT, (.4, 1, .4))
    else:
        draw_mouth(k, 0, 58.5, 7.2, mouth_, emo)
    _accessory(k, sp, 45, 14, 80, kind="animal")


def _shellbeast(k, sp, mouth_, eyes, emo, arms):
    a = _A(k, sp)
    m, b = a.m, a.b
    shell_col = a.look.get("shell") or (150, 110, 70)
    sh = k.egg(0, 72, 24, 22, top=.9)
    k.part(sh, shell_col)
    for i, (dx, dy) in enumerate(((-13, 66), (0, 62), (13, 66), (-17, 79), (17, 79))):
        k.clip_paste(sh, k.poly([(dx + 4.5 * math.cos(math.radians(60 * j)), dy + 4.5 * math.sin(math.radians(60 * j))) for j in range(6)]),
                     lighten(shell_col, .22))
    k.form(sh, .3, .45)
    a.build = "normal"
    for sx in (-1, 1):
        k.part(k.egg(sx * 9, 90, 5.6, 6.6, top=.95), m)
        k.part(k.egg(sx * 9.5, 95.2, 7, 4.1, top=1.05), darken(m, .06), shade=(.25, .35))
    bsh = k.egg(0, 78, 13.5, 14, top=.82)
    k.part(bsh, (240, 220, 150))
    for yy in (72, 78, 84):
        k.stroke([(-9, yy), (9, yy)], .9, (200, 175, 110), (.4, 1, .4))
    k.form(bsh, .3, .4)
    a.hy = 41
    two_arms(k, arms, (12, 69), 12, 3.3, m, "paw", clap_x=3, layer="low")
    head = k.egg(0, 41, 20, 17, top=.95)
    k.occlude(bsh, head, 3)
    k.part(head, m)
    k.fill(k.E(0, 50, 9, 5), lighten(b, .1))
    for dx, dy in ((-11, 31), (12, 33), (-14, 38)):
        k.fill(k.E(dx, dy, 1.4, 1.1), darken(m, .12))
    k.form(head, .3, .5, .18)
    two_arms(k, arms, (12, 69), 13, 3.3, m, "paw", layer="high")
    a.ey = 39
    _face(a, mouth_, eyes, emo, ("dots", 0, 46.5, .7, 51, 4.6))
    _accessory(k, sp, 41, 17, 78, kind="animal")


def _croc(k, sp, mouth_, eyes, emo, arms):
    a = _A(k, sp)
    m, b = a.m, a.b
    a.look["tail"] = "thick"
    _tail(a)
    bsh = _body(a)
    for i in range(4):                                 # back ridge bumps on the shoulders
        k.part(k.E(-14 + i * 9.3, 60.5 - (1 if i in (1, 2) else 0), 2.4, 2.0), darken(m, .1), k.li * .8)
    two_arms(k, arms, (16.5, 65), 12, 3.8, m, "paw", clap_x=3.2, layer="low")
    hy = 38
    for sx in (-1, 1):
        k.ink(k.E(sx * 9.5, hy - 10, 8.5, 8))
    head = k.egg(0, hy, 23, 16, top=.9)
    snout = k.egg(0, hy + 12, 19, 8.5, top=1.0)
    k.occlude(bsh, snout, 3.0)
    k.ink(head)
    k.ink(snout)
    for sx in (-1, 1):
        k.fill(k.E(sx * 9.5, hy - 10, 8.5, 8), m)
    k.fill(head, m)
    k.fill(snout, lighten(m, .12))
    for sx in (-1, 1):
        k.part(k.E(sx * 4, hy + 6.8, 1.6, 1.2), darken(m, .1), k.li * .7)
        k.fill(k.E(sx * 4, hy + 6.6, .7, .5), darken(m, .55))
    k.form(head, .3, .5, .18)
    k.form(snout, .25, .4)
    for sx in (-1, 1):
        k.form(k.E(sx * 9.5, hy - 10, 8.5, 8), .2, .45)
    two_arms(k, arms, (16.5, 65), 13, 3.8, m, "paw", layer="high")
    for sx in (-1, 1):
        eye(k, sx * 9.5, hy - 9.5, 6.4, sx, eyes, emo, iris=(140, 110, 30), brow_col=darken(m, .5))
    k.blush(-17, hy + 4, 3.6, 2.3)
    k.blush(17, hy + 4, 3.6, 2.3)
    my = hy + 13.5
    if mouth_ == 0:
        curve = MOUTH[emo][0]
        k.stroke([(x, my - curve * 3 * (x / 15) ** 2) for x in [-15 + i * 1.875 for i in range(17)]], 1.3, OUT, (.4, 1, .4))
        for x in (-10, -5, 5, 10):                     # friendly little tooth bumps
            yy = my - curve * 3 * (x / 15) ** 2
            k.part(k.poly([(x - 1.2, yy + .5), (x, yy + 2.4), (x + 1.2, yy + .5)]), (255, 255, 255), k.li * .6)
    else:
        draw_mouth(k, 0, my, 9, mouth_, emo, teeth=True)
    _accessory(k, sp, hy, 16, 77, kind="animal")


PLANS = {"bird": _bird, "bug": _bug, "fish": _fish, "snake": _snake, "frog": _frog, "shell": _shellbeast, "croc": _croc}


def _animal(d, W, H, sp, mouth, eyes, emo, arms):
    k = Toon(d, W, H)
    key = sp.get("_key") or sp.get("species")
    plan = LOOK.get(key, {}).get("plan", "mammal")
    PLANS.get(plan, _mammal)(k, sp, mouth, eyes, emo, arms)


# ================================================================= humans
HAIR_STYLES = ("short", "long", "curly", "bun", "braids", "bald", "spiky", "afro", "ponytail")
ROYAL = ("king", "queen", "prince", "princess", "emperor")


def _human_dress(sp) -> str:
    """Body garment from outfit + role: shirt | dress | robe | armor | overalls | apron | sailor."""
    o, words = sp.get("outfit") or "none", sp.get("_words", "")
    if o in ("dress", "robe"):
        return o
    if any(w in words for w in ("wizard", "monk", "witch", "emperor")):
        return "robe"
    if any(w in words for w in ("princess", "queen", "fairy")):
        return "dress"
    if o == "helmet" or "knight" in words:
        return "armor"
    if "farmer" in words:
        return "overalls"
    if o == "chef_hat" or "baker" in words or "cook" in words:
        return "apron"
    if "sailor" in words or "fisherman" in words:
        return "sailor"
    return "shirt"


def _human(d, W, H, sp, mouth_, eyes, emo, arms):
    k = Toon(d, W, H)
    skin, hair, main = sp["skin_rgb"], sp["hair_rgb"], sp["main"]
    words = sp.get("_words", "")
    gender = str(sp.get("gender", "")).lower()
    female = gender.startswith("f")
    old, child = sp["age"] == "old", sp["age"] == "child"
    style = sp.get("hair") if sp.get("hair") in HAIR_STYLES else ("bald" if old and gender.startswith("m") else "short")
    if old and str(sp.get("hair_color", "")).lower() not in HAIRS:
        hair = HAIRS["grey"]
    dress = _human_dress(sp)
    royal = any(w in words for w in ROYAL) or sp.get("outfit") == "crown"
    hy, R = 36.5, 19.0
    if child:
        hy, R = 38.5, 20.0
    neck_y = hy + R * .95
    shoulder_y = hy + R + 2.5
    tw = 10.5 if not child else 9.5
    acc = sp["accent"]
    sk_tint = SKIN_SHADOW
    # --- behind everything: wings, cape, back hair
    if sp.get("outfit") == "wings" or "fairy" in words:
        for sx in (-1, 1):
            for ang, rx, ry, dy in ((-35, 15, 9, 50), (25, 10, 6.5, 66)):
                w = k.rot_ell(sx * 20, dy, rx, ry, sx * ang)
                k.glaze(w, (200, 235, 255), .75)
                _outline(k, w, k.li)
    if sp.get("outfit") == "cape" or royal:
        cape_col = (200, 45, 75) if royal else (200, 50, 70)
        k.part(k.poly(_bez([(-tw - 1, shoulder_y), (-tw - 9, 80), (-tw - 7, 94)], 10) + [(tw + 7, 94)] +
                      _bez([(tw + 7, 94), (tw + 9, 80), (tw + 1, shoulder_y)], 10)[1:]), cape_col, shade=(.3, .3))
    _hair_back(k, style, hair, hy, R, female, acc)
    # --- legs + shoes
    pants = darken(main, .4) if dress in ("shirt", "sailor", "apron") else ((70, 100, 170) if dress == "overalls" else
                                                                           ((170, 175, 190) if dress == "armor" else skin))
    for sx in (-1, 1):
        k.part(k.tube([(sx * 4.6, 80), (sx * 4.8, 92)], [3.4, 3.2]), pants)
        k.part(k.egg(sx * 5.6, 95.0, 5.6, 3.4, top=1.15), (85, 60, 70) if not royal else (150, 40, 60), shade=(.25, .4))
        k.fill(k.E(sx * 5.6 - 1.5, 93.8, 1.6, .7), (160, 140, 150))
    # --- torso garment
    tcol = main if dress != "armor" else (185, 192, 210)
    if dress == "dress":
        torso = k.poly(_bez([(-tw + 1, shoulder_y - 1), (-tw - 1, 72), (-tw - 7, 88)], 10) + _bez([(-tw - 7, 88), (0, 91), (tw + 7, 88)], 10)[1:] +
                       _bez([(tw + 7, 88), (tw - 1, 72), (tw - 1, shoulder_y - 1)], 10)[1:] + [(0, shoulder_y - 3)])
        k.part(torso, tcol)
        k.clip_paste(torso, k.scallop(0, 89, tw + 9, 3.2, 16, .25), lighten(tcol, .45))
        k.stroke([(-tw + 1, 68), (tw - 1, 68)], 1.6, darken(tcol, .2), (1, 1, 1))
    elif dress == "robe":
        torso = k.poly(_bez([(-tw + 1, shoulder_y - 1), (-tw - 2, 75), (-tw - 4, 94)], 10) + [(tw + 4, 94)] +
                       _bez([(tw + 4, 94), (tw + 2, 75), (tw - 1, shoulder_y - 1)], 10)[1:] + [(0, shoulder_y - 3)])
        k.part(torso, tcol)
        k.clip_paste(torso, k.poly([(-tw - 6, 72), (tw + 6, 72), (tw + 6, 75.5), (-tw - 6, 75.5)]), acc)
        k.stroke([(0, shoulder_y + 1), (0, 93)], 1.0, darken(tcol, .25), (1, 1, 1))
        if "wizard" in words:
            for x, y in ((-6, 82), (5, 86), (-3, 90), (7, 79)):
                _star(k, x, y, 1.6, (255, 225, 110))
    else:
        torso = k.poly(_bez([(-tw, shoulder_y - 1), (-tw - 1.6, 70), (-tw - .5, 83)], 10) + _bez([(-tw - .5, 83), (0, 84.5), (tw + .5, 83)], 8)[1:] +
                       _bez([(tw + .5, 83), (tw + 1.6, 70), (tw, shoulder_y - 1)], 10)[1:] + [(0, shoulder_y - 3)])
        k.part(torso, tcol)
        if dress == "overalls":
            bib = k.poly([(-7, 67), (7, 67), (8.5, 84), (-8.5, 84)])
            k.clip_paste(torso, bib, (70, 100, 170))
            for sx in (-1, 1):
                k.clip_paste(torso, k.tube([(sx * 7, shoulder_y), (sx * 6, 67)], [1.2, 1.2]), (70, 100, 170))
                k.part(k.E(sx * 5.8, 68.5, 1.1, 1.1), (255, 215, 90), k.li * .6)
            k.clip_paste(torso, k.poly([(-4, 72), (4, 72), (3.5, 77), (-3.5, 77)]), darken((70, 100, 170), .15))
        elif dress == "apron":
            k.clip_paste(torso, k.poly([(-7.5, 64), (7.5, 64), (9, 84), (-9, 84)]), (255, 255, 255))
            k.clip_paste(torso, k.poly([(-3.4, 71), (3.4, 71), (3.4, 75), (-3.4, 75)]), (235, 235, 240))
        elif dress == "armor":
            k.clip_paste(torso, k.poly([(-tw - 2, 76), (tw + 2, 76), (tw + 2, 79), (-tw - 2, 79)]), (120, 90, 70))
            k.part(k.blob(0, 69, 4.4, 5.2, [(90, 30, .25)]), acc, k.li, (.2, .4))
        elif dress == "sailor":
            k.clip_paste(torso, k.poly([(-tw - 2, shoulder_y - 2), (tw + 2, shoulder_y - 2), (0, 70)]), (255, 255, 255))
            k.clip_paste(torso, k.poly([(-tw + 1.5, shoulder_y - 2), (tw - 1.5, shoulder_y - 2), (0, 67)]), tcol)
            k.part(k.poly([(-2.5, 66.5), (2.5, 66.5), (0, 71)]), (230, 70, 80), k.li * .7)
        else:
            k.clip_paste(torso, k.poly([(-tw - 2, 80), (tw + 2, 80), (tw + 2, 84), (-tw - 2, 84)]), darken(main, .3))
            for yy in (67, 72.5):
                k.part(k.E(0, yy, .9, .9), lighten(main, .5), k.li * .5)
    k.form(torso, .3, .4)
    # neckline / royal ermine collar / scarf
    if royal:
        col = k.poly(_bez([(-tw - 2, shoulder_y - .5), (0, shoulder_y + 6), (tw + 2, shoulder_y - .5)], 10) +
                     _bez([(tw + 2, shoulder_y - .5), (0, shoulder_y + 1.5), (-tw - 2, shoulder_y - .5)], 10)[1:])
        k.part(col, (255, 252, 245), k.li, (.2, .3))
        for x in (-7, -2.5, 2.5, 7):
            k.fill(k.E(x, shoulder_y + 2 + (1.6 if abs(x) < 4 else 0), .6, .9), (50, 45, 55))
    elif sp.get("outfit") == "scarf":
        k.part(k.tube([(-tw + 1, shoulder_y + 1), (tw - 1, shoulder_y + 1)], [2.6, 2.6]), (230, 70, 80), shade=(.2, .3))
        k.part(k.tube([(tw - 4, shoulder_y + 1), (tw - 3, shoulder_y + 10)], [2.0, 2.0]), (230, 70, 80), k.li)
    # --- arms (sleeves + skin hands)
    sleeve = tcol if dress != "dress" else lighten(tcol, .1)
    two_arms(k, arms, (tw - .5, shoulder_y + 2.5), 13.5, 2.8, sleeve, "hand", hand_col=skin, clap_x=2.8, layer="low")
    if style == "braids":
        _braids(k, hair, hy, R, acc)
    # --- neck, ears, head
    k.part(k.tube([(0, neck_y - 3), (0, neck_y + 3)], [3.3, 3.3]), darken(skin, .08), k.li * .8)
    for sx in (-1, 1):
        ear = k.E(sx * R * .98, hy + 2, 3.2, 3.9)
        k.part(ear, skin)
        k.fill(k.E(sx * R * .98 + sx * .3, hy + 2.3, 1.6, 2.2), darken(skin, .12))
        if female and not child and style not in ("long", "afro", "curly"):
            k.part(k.E(sx * R * .98, hy + 6.4, 1.1, 1.1), acc, k.li * .6)
    head = k.egg(0, hy, R, R * 1.0, top=.98, bot=1.0)
    k.part(head, skin)
    if old:
        for sx in (-1, 1):
            k.stroke(_bez([(sx * 11.5, hy + 4), (sx * 12.5, hy + 7), (sx * 11.2, hy + 10)], 6), .7, darken(skin, .25), (.2, 1, .2))
    k.form(head, .2, .45, .16, tint=sk_tint)
    _hair_front(k, style, hair, hy, R, female, old, child, acc)
    # --- face
    ey = hy + 1.5
    iris = _col(sp.get("eye_color")) or (95, 60, 40)
    lash = female
    brow = darken(hair, .25) if sum(hair) < 600 else (150, 140, 150)
    for sx in (-1, 1):
        eye(k, sx * 7.4, ey, 6.2, sx, eyes, emo, iris=iris, lash=lash, brow_col=brow, wide=.74)
    k.blush(-12.5, hy + 8.5, 3.4, 2.0, alpha=.45)
    k.blush(12.5, hy + 8.5, 3.4, 2.0, alpha=.45)
    if sp.get("freckles") or (child and not female and sp["skin_rgb"][0] > 220):
        for dx, dy in ((-13, 7), (-11.5, 8.2), (-14, 9), (13, 7), (11.5, 8.2), (14, 9)):
            k.fill(k.E(dx, hy + dy - 1.5, .45, .45), darken(skin, .3))
    k.stroke(_bez([(-1.0, hy + 5.6), (.5, hy + 7.2), (1.4, hy + 6)], 6), 1.0, darken(skin, .32), (.4, 1, .6))   # nose
    beard = old and gender.startswith("m") and sp.get("beard") is not False
    my = hy + 10.5
    if beard:
        k.part(k.scallop(0, hy + 14.5, 11.5, 7.5, 11, .18), hair if sum(hair) > 450 else HAIRS["white"], shade=(.2, .35))
        k.fill(k.E(0, my + .5, 4.6, 2.6), skin)
    draw_mouth(k, 0, my, 4.0, mouth_, emo)
    if beard or (sp.get("moustache")):
        for sx in (-1, 1):
            k.part(k.rot_ell(sx * 2.8, my - 1.6, 3.2, 1.6, sx * -12), hair if sum(hair) > 450 else HAIRS["white"], k.li, (.2, .3))
    if old or sp.get("outfit") == "glasses" or sp.get("glasses"):
        frame_c = (120, 80, 60)
        for sx in (-1, 1):
            ex_, ey_ = k.P(sx * 7.4, ey)
            Rg = 6.6 * k.u
            lens = ("e", ex_, ey_, Rg, Rg * .9)
            k.glaze(lens, (230, 240, 255), .15)
            k.clip_paste(lens, k.poly([(sx * 7.4 - 4.4, ey - .5), (sx * 7.4 - 1.6, ey - 5.2), (sx * 7.4, ey - 4.9), (sx * 7.4 - 3, ey)]), (255, 255, 255), .55)
            k.d.ellipse([ex_ - Rg, ey_ - Rg * .9, ex_ + Rg, ey_ + Rg * .9], outline=frame_c, width=max(1, int(k.u * 1.0)))
        k.stroke(_bez([(-1.0, ey - .6), (0, ey - 1.6), (1.0, ey - .6)], 6), 1.0, frame_c, (1, 1, 1))
    # --- hats & accessories
    _accessory(k, sp, hy, R, 70, kind="human", hair=hair, style=style)
    two_arms(k, arms, (tw - .5, shoulder_y + 2.5), 14.5, 2.8, sleeve, "hand", hand_col=skin, layer="high")


def _star(k, x, y, r, col):
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        rr = r if i % 2 == 0 else r * .45
        pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
    k.part(k.poly(pts), col, k.li * .6)


def _hair_back(k, style, hair, hy, R, female, acc):
    if style == "long":
        k.part(k.poly(_bez([(-R * .95, hy - R * .4), (-R * 1.25, hy + R * .6), (-R * 1.0, hy + R * 1.45)], 12) +
                      _bez([(-R * 1.0, hy + R * 1.45), (0, hy + R * 1.6), (R * 1.0, hy + R * 1.45)], 10)[1:] +
                      _bez([(R * 1.0, hy + R * 1.45), (R * 1.25, hy + R * .6), (R * .95, hy - R * .4)], 12)[1:] +
                      _bez([(R * .95, hy - R * .4), (0, hy - R * 1.3), (-R * .95, hy - R * .4)], 10)[1:]), hair, shade=(.3, .35))
    elif style == "afro":
        k.part(k.scallop(0, hy - R * .15, R * 1.38, R * 1.3, 14, .12), hair, shade=(.3, .35))
    elif style == "curly":
        k.part(k.scallop(0, hy + R * .05, R * 1.22, R * 1.2, 13, .16), hair, shade=(.3, .35))
    elif style == "bun":
        k.part(k.E(0, hy - R * 1.08, R * .44, R * .4), hair, shade=(.3, .4))
        k.stroke(_bez([(-R * .3, hy - R * 1.12), (0, hy - R * .95), (R * .3, hy - R * 1.12)], 6), .8, darken(hair, .3), (.3, 1, .3))
    elif style == "ponytail":
        p = _bez([(R * .5, hy - R * .85), (R * 1.35, hy - R * .9), (R * 1.45, hy + R * .3), (R * 1.15, hy + R * 1.1)], 16)
        k.part(k.tube(p, [3.4, 5.2, 4.8, 1.6]), hair, shade=(.3, .35))
        k.part(k.E(p[2][0], p[2][1], 2.2, 2.4), acc, k.li * .8)


def _braids(k, hair, hy, R, acc):
    for sx in (-1, 1):
        x0, y0 = sx * R * .86, hy + R * .35
        for j in range(5):
            y = y0 + j * 3.6
            k.part(k.rot_ell(x0 + sx * j * .25, y, 2.9 - j * .12, 2.3, sx * 20), hair, k.li, (.2, .3))
        yb = y0 + 5 * 3.6 - .8
        k.part(k.E(x0 + sx * 1.3, yb, 1.7, 1.5), acc, k.li * .8, (.15, .4))
        k.part(k.tube([(x0 + sx * 1.3, yb + 1), (x0 + sx * 1.5, yb + 4)], [1.4, .5]), hair, k.li * .8)


def _hair_front(k, style, hair, hy, R, female, old, child, acc):
    if style in ("bald",):
        k.glaze(k.rot_ell(-6, hy - R * .62, 4.5, 2.0, -25), (255, 255, 255), .35)
        for sx in (-1, 1):
            k.part(k.scallop(sx * R * .93, hy - 2.5, 3.4, 5.2, 6, .3), hair, k.li, (.2, .3))
        return
    top = [(math.cos(math.radians(a)) * R * 1.07, hy + math.sin(math.radians(a)) * R * 1.07) for a in range(168, 373, 6)]
    rgt, lft = top[-1], top[0]
    if style in ("long", "braids", "bun", "ponytail") and (female or style != "ponytail"):
        line = _bez([rgt, (R * .95, hy - R * .55), (R * .1, hy - R * .55), (0, hy - R * .72)], 12) + \
            _bez([(0, hy - R * .72), (-R * .1, hy - R * .55), (-R * .95, hy - R * .55), lft], 12)[1:]
    elif style == "spiky":
        line = _bez([rgt, (R * .7, hy - R * .3), (-R * .2, hy - R * .55), lft], 16)
        spikes = []
        for i, (ang, ln) in enumerate(((200, 1.25), (230, 1.38), (262, 1.42), (292, 1.36), (322, 1.25))):
            a1, a2 = math.radians(ang - 14), math.radians(ang + 14)
            am = math.radians(ang + 4)
            spikes.append(k.poly([(math.cos(a1) * R, hy + math.sin(a1) * R), (math.cos(am) * R * ln, hy + math.sin(am) * R * ln),
                                  (math.cos(a2) * R, hy + math.sin(a2) * R)]))
        for sh in spikes:
            k.part(sh, hair, shade=(.25, .35))
    elif style == "afro":
        line = _bez([rgt, (R * .7, hy - R * .7), (-R * .7, hy - R * .7), lft], 16)
    elif style == "curly":
        line = [(math.cos(math.radians(a)) * R * .9, hy - R * .25 + math.sin(math.radians(a)) * R * .45 + (1.2 if (a // 15) % 2 else 0))
                for a in range(360, 175, -15)]
    else:   # short: side-swept fringe
        line = _bez([rgt, (R * .9, hy - R * .25), (R * .5, hy - R * .5), (-R * .2, hy - R * .42)], 12) + \
            _bez([(-R * .2, hy - R * .42), (-R * .7, hy - R * .3), (-R * .85, hy - R * .2), lft], 10)[1:]
    cap = k.poly(top + line)
    if style == "curly":
        cap = k.poly([(math.cos(math.radians(a)) * R * (1.1 + .07 * math.sin(math.radians(a) * 13)),
                       hy + math.sin(math.radians(a)) * R * (1.1 + .07 * math.sin(math.radians(a) * 13))) for a in range(170, 371, 4)] + line)
    k.part(cap, hair)
    for j, (x0, x1) in enumerate(((-.5, -.2), (.15, .45), (.55, .75))):         # strand shine
        if style in ("short", "long", "bun", "ponytail", "braids", "spiky"):
            k.stroke(_bez([(R * x0, hy - R * .82), (R * (x0 + x1) / 2 + .5, hy - R * .95), (R * x1, hy - R * .7)], 6), .9,
                     darken(hair, .25), (.2, 1, .2))
    k.form(cap, .26, .5, .18, col=hair)
    if style == "bun" or (female and style in ("long", "ponytail") and not old):
        pass


def _accessory(k, sp, hy, R, by, kind="human", hair=None, style=None):
    o = sp.get("outfit") or "none"
    top = hy - R * (1.02 if kind == "human" else .96)
    gold = (255, 205, 60)
    if o == "crown":
        pts = [(-R * .62, top + 3.5), (-R * .7, top - 6), (-R * .35, top - 1.5), (0, top - 8), (R * .35, top - 1.5),
               (R * .7, top - 6), (R * .62, top + 3.5)]
        sh = k.poly(pts)
        k.part(sh, gold, shade=(.25, .45))
        k.clip_paste(sh, k.poly([(-R, top + 1), (R, top + 1), (R, top + 3.6), (-R, top + 3.6)]), darken(gold, .12))
        for x, y in ((-R * .7, top - 6), (0, top - 8), (R * .7, top - 6)):
            k.part(k.E(x, y, 1.4, 1.4), (255, 240, 160), k.li * .6)
        k.part(k.E(0, top + .5, 1.6, 1.8), (230, 60, 95), k.li * .6, (.1, .5))
        for sx in (-1, 1):
            k.part(k.E(sx * R * .38, top + 1.2, 1.0, 1.1), (80, 160, 230), k.li * .5)
    elif o == "wizard_hat":
        col = (110, 80, 190)
        apex = max(top - 26, 1.5)
        hat = k.poly(_bez([(-R * .78, top + 4), (-R * .3, top - 8), (2, apex + 6), (10, apex)], 14) +
                     _bez([(10, apex), (6, apex + 9), (R * .4, top - 6), (R * .78, top + 4)], 14)[1:])
        k.part(hat, col, shade=(.3, .4))
        k.clip_paste(hat, k.poly([(-R, top + .2), (R, top + .2), (R, top + 3.4), (-R, top + 3.4)]), gold)
        _star(k, -2, top - 7, 2.2, (255, 230, 120))
        _star(k, 4, top - 14, 1.5, (255, 230, 120))
        k.part(k.egg(0, top + 4.5, R * 1.25, 3.0, top=1.1), col, shade=(.2, .3))
    elif o in ("cap", "chef_hat", "straw_hat", "turban", "helmet", "feathers", "bow"):
        if o == "straw_hat":
            col = (240, 205, 120)
            k.part(k.egg(0, top + 4.5, R * 1.45, 3.6, top=1.1), col, shade=(.2, .35))
            crown = k.egg(0, top, R * .72, 6.5, top=.85)
            k.part(crown, col, shade=(.25, .4))
            k.clip_paste(crown, k.poly([(-R, top + 1.5), (R, top + 1.5), (R, top + 4.5), (-R, top + 4.5)]), (220, 70, 70))
            for x in (-6, -2, 2, 6):
                k.stroke([(x, top - 4), (x * 1.1, top + 1)], .6, darken(col, .2), (1, 1, 1))
        elif o == "chef_hat":
            k.group([k.E(dx, top - 6 - (2 if dx == 0 else 0), 5.4, 5.4) for dx in (-6, 0, 6)], (255, 255, 255), shade=(.2, .35))
            k.part(k.poly([(-R * .62, top - 4), (R * .62, top - 4), (R * .6, top + 4), (-R * .6, top + 4)]), (255, 255, 255), shade=(.2, .3))
        elif o == "cap":
            col = (60, 110, 200) if "sailor" not in sp.get("_words", "") else (255, 255, 255)
            capsh = k.poly([(math.cos(math.radians(a)) * R * 1.05, top + 5 + math.sin(math.radians(a)) * 9.5) for a in range(180, 361, 10)])
            k.part(capsh, col, shade=(.25, .4))
            if "sailor" in sp.get("_words", ""):
                k.clip_paste(capsh, k.poly([(-R * 1.2, top + 2), (R * 1.2, top + 2), (R * 1.2, top + 5), (-R * 1.2, top + 5)]), (40, 60, 120))
            else:
                k.part(k.egg(-R * .55, top + 5, R * .7, 2.2, top=1.0), darken(col, .15), shade=(.2, .3))
                k.part(k.E(0, top - 4.2, 1.2, 1.0), darken(col, .2), k.li * .6)
        elif o == "turban":
            col = (240, 120, 60)
            t = k.scallop(0, top + 1, R * .95, 7.5, 7, .14)
            k.part(t, col, shade=(.25, .4))
            for j in (-1, 1):
                k.stroke(_bez([(-R * .8, top + 2 + j * 2), (0, top - 3 + j * 2), (R * .8, top + 2 + j * 2)], 8), .9, darken(col, .2), (.2, 1, .2))
            k.part(k.E(0, top + 2.5, 1.8, 2.1), (60, 170, 200), k.li * .7, (.1, .5))
        elif o == "helmet":
            col = (190, 195, 210)
            hel = k.poly([(math.cos(math.radians(a)) * R * 1.1, top + 8 + math.sin(math.radians(a)) * 14) for a in range(180, 361, 8)])
            k.part(hel, col, shade=(.3, .5))
            k.clip_paste(hel, k.poly([(-1.4, top - 8), (1.4, top - 8), (1.4, top + 9), (-1.4, top + 9)]), darken(col, .15))
            k.part(k.tube(_bez([(0, top - 5), (4, top - 12), (10, top - 10)], 8), [2.6, 3.0, 1.0]), (230, 60, 70), shade=(.2, .3))
        elif o == "feathers":
            k.part(k.tube([(-R * .95, top + 4.5), (R * .95, top + 4.5)], [1.8, 1.8]), (200, 120, 60), shade=(.2, .3))
            for i, dx in enumerate((-4.5, 0, 4.5)):
                col = [(230, 80, 70), (255, 200, 60), (80, 170, 230)][i]
                k.part(k.rot_ell(dx, top - 3, 2.2, 6.5, dx * 3), col, shade=(.2, .35))
                k.stroke([(dx * .9, top + 2), (dx * 1.2, top - 8)], .6, darken(col, .35), (1, 1, 1))
        elif o == "bow":
            x0 = R * .55 if kind == "human" else R * .5
            for sx in (-1, 1):
                k.part(k.poly(_bez([(x0, top + 3), (x0 + sx * 6, top - 2), (x0 + sx * 6, top + 7)], 8) + [(x0, top + 3)]),
                       (240, 90, 150), shade=(.2, .35))
            k.part(k.E(x0, top + 3, 1.8, 1.8), (220, 60, 120), k.li * .7)
    elif o == "scarf" and kind != "human":
        k.part(k.tube([(-12, by - 13), (12, by - 13)], [2.6, 2.6]), (230, 70, 80), shade=(.2, .3))
        k.part(k.tube([(8, by - 13), (9, by - 5)], [2.0, 2.0]), (230, 70, 80), k.li)
    elif o == "glasses" and kind != "human":
        for sx in (-1, 1):
            ex_, ey_ = k.P(sx * 8.6, hy - 1.5)
            Rg = 8.6 * k.u
            k.d.ellipse([ex_ - Rg, ey_ - Rg, ex_ + Rg, ey_ + Rg], outline=(80, 60, 50), width=max(1, int(k.u * 1.1)))


def draw(d, W, H, spec: dict, mouth: int, eyes: str, emotion: str, arms: str):
    sp = normalize(spec)
    (_human if sp["kind"] == "human" else _animal)(d, W, H, sp, mouth, eyes, emotion, arms)


@lru_cache(maxsize=180)
def sprite_from_json(spec_json: str, height: int, mouth: int = 0, eyes: str = "open", emotion: str = "happy",
                     arms: str = "down"):
    spec = json.loads(spec_json)
    sp = normalize(spec)
    h = max(8, int(height * sp.get("size", 1.0)))
    ss = base.supersample(h)
    H = h * ss
    W = int(h * (1.05 if sp["kind"] == "animal" else .9)) * ss
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw(ImageDraw.Draw(im), W, H, spec, max(0, min(2, int(mouth))), "closed" if eyes == "closed" else "open",
         emotion if emotion in base.EMOTIONS else "happy", arms if arms in base.ARMS else "down")
    return base.shade(base._finish(im, ss))
