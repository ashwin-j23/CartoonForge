"""Backgrounds ("sets"), drawn in code at the render size and cached.

Soft-saturated, low-detail on purpose: the characters and the card must be the brightest, clearest thing on
screen (figure/ground contrast for young eyes). Each set has a few gently moving overlay elements (clouds
drift, stars twinkle, bubbles rise, snow falls) so the world feels alive without fast motion.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from .common import OUT, darken, lighten
from .icons import icon

GROUND = 0.80          # horizon/floor line as a fraction of height

# id: (kind, sky_top, sky_bottom, ground, extras, overlay)
SETS: dict[str, dict] = {
    "meadow": {"sky": ((140, 205, 255), (215, 240, 255)), "ground": (125, 205, 110), "hills": [(160, 220, 130), (110, 190, 100)],
               "props": [("tree", .08, .74, .26), ("tree", .93, .72, .3), ("flower", .3, .9, .07), ("flower", .62, .93, .06),
                         ("flower", .82, .9, .07), ("butterfly", .7, .35, .06)], "overlay": "clouds"},
    "farm": {"sky": ((150, 210, 255), (225, 242, 255)), "ground": (150, 200, 100), "hills": [(180, 215, 120), (140, 190, 90)],
             "props": [("house", .12, .7, .28), ("tree", .9, .72, .28), ("cow", .78, .86, .1)], "fence": True, "overlay": "clouds"},
    "beach": {"sky": ((120, 200, 255), (220, 245, 255)), "ground": (250, 225, 160), "sea": (70, 170, 230),
              "props": [("shell", .2, .92, .06), ("shell", .7, .95, .05), ("tree", .92, .7, .32), ("boat", .55, .66, .08)],
              "overlay": "clouds"},
    "classroom": {"wall": (255, 240, 200), "floor": (220, 180, 130), "board": True, "abc": True,
                  "props": [("book", .9, .74, .08), ("block", .82, .9, .07)], "window": True},
    "garden": {"sky": ((150, 215, 255), (230, 245, 255)), "ground": (130, 210, 115), "hills": [(170, 225, 140)],
               "props": [("flower", .1, .86, .1), ("flower", .2, .9, .08), ("flower", .85, .88, .1), ("flower", .93, .92, .08),
                         ("carrot", .4, .95, .05), ("bee", .75, .4, .05)], "fence": True, "overlay": "clouds"},
    "playground": {"sky": ((140, 205, 255), (215, 240, 255)), "ground": (130, 205, 120), "hills": [(170, 220, 135)],
                   "slide": True, "props": [("ball", .7, .92, .06), ("kite", .8, .25, .09), ("tree", .06, .72, .26)],
                   "overlay": "clouds"},
    "jungle": {"sky": ((150, 220, 190), (210, 245, 215)), "ground": (90, 170, 90), "hills": [(70, 150, 90), (60, 135, 80)],
               "props": [("tree", .05, .7, .36), ("tree", .95, .7, .36), ("leaf", .15, .9, .12), ("leaf", .88, .92, .12),
                         ("bird", .7, .25, .07)], "vines": True, "overlay": "leaves"},
    "ocean": {"sky": ((70, 160, 230), (30, 100, 190)), "ground": (240, 215, 160), "underwater": True,
              "props": [("fish", .15, .3, .08), ("fish", .85, .45, .07), ("shell", .3, .93, .05), ("shell", .78, .95, .05)],
              "seaweed": True, "overlay": "bubbles"},
    "forest": {"sky": ((170, 220, 250), (225, 245, 240)), "ground": (110, 180, 95), "hills": [(90, 160, 100), (80, 150, 90)],
               "props": [("tree", .04, .7, .34), ("tree", .18, .72, .26), ("tree", .84, .72, .28), ("tree", .97, .7, .34),
                         ("snail", .7, .94, .05)], "overlay": "leaves"},
    "snow": {"sky": ((170, 205, 245), (230, 240, 255)), "ground": (245, 250, 255), "hills": [(225, 235, 250), (210, 225, 245)],
             "props": [("tree", .08, .72, .26), ("snowflake", .8, .3, .06)], "overlay": "snow"},
    "savanna": {"sky": ((255, 210, 150), (255, 240, 200)), "ground": (225, 200, 110), "hills": [(215, 185, 110)],
                "acacia": True, "props": [("elephant", .88, .84, .12), ("bird", .2, .25, .05)], "overlay": "clouds"},
    "village": {"sky": ((150, 210, 255), (225, 242, 255)), "ground": (160, 205, 120), "hills": [(180, 220, 140)],
                "props": [("house", .08, .7, .24), ("house", .9, .7, .24), ("tree", .22, .72, .2), ("lantern", .75, .3, .07)],
                "overlay": "clouds"},
    "night": {"sky": ((25, 35, 85), (70, 70, 140)), "ground": (60, 90, 110), "hills": [(45, 70, 100), (55, 85, 110)],
              "props": [("moon", .85, .2, .14), ("house", .1, .72, .2)], "overlay": "stars", "dark": True},
    "bedroom": {"wall": (190, 200, 245), "floor": (170, 140, 190), "bed": True, "window_night": True,
                "props": [("book", .08, .9, .07), ("lamp", .9, .78, .07)], "dark": True},
    "lab": {"wall": (215, 240, 240), "floor": (180, 200, 210), "table": True, "flasks": True,
            "props": [("planet", .1, .3, .1)], "window": True},
    "sky": {"sky": ((110, 190, 255), (200, 235, 255)), "clouds_big": True,
            "props": [("balloon", .1, .35, .1), ("plane", .82, .22, .1), ("bird", .25, .15, .05), ("rainbow", .5, .82, .4)],
            "overlay": "clouds"},
    "space": {"sky": ((15, 15, 45), (45, 30, 90)), "ground": (150, 150, 175), "moonground": True,
              "props": [("planet", .85, .25, .16), ("star", .15, .2, .05), ("rocket", .08, .55, .12)], "overlay": "stars",
              "dark": True},
    "volcano_valley": {"sky": ((255, 200, 160), (255, 235, 200)), "ground": (120, 180, 90), "volcano": True,
                       "props": [("tree", .05, .72, .3), ("egg", .78, .93, .05), ("leaf", .95, .9, .12)], "overlay": "clouds"},
    "city": {"sky": ((150, 210, 255), (225, 242, 255)), "ground": (170, 175, 185), "buildings": True,
             "props": [("tree", .05, .74, .2), ("bus", .82, .88, .14)], "overlay": "clouds"},
    "road": {"sky": ((150, 210, 255), (225, 242, 255)), "ground": (130, 200, 110), "hills": [(170, 220, 140)], "road": True,
             "props": [("tree", .08, .7, .24), ("car", .85, .9, .12), ("house", .93, .66, .16)], "overlay": "clouds"},
    "kitchen": {"wall": (255, 235, 210), "floor": (230, 200, 160), "counter": True,
                "props": [("cup", .82, .66, .06), ("apple", .9, .66, .05), ("cake", .72, .65, .07)], "window": True},
    "world_map": {"sky": ((90, 170, 240), (130, 200, 250)), "map": True, "props": [("plane", .5, .12, .08)]},
    "storybook": {"wall": (255, 225, 190), "floor": (190, 130, 90), "shelves": True, "window": True,
                  "props": [("book", .9, .9, .09), ("lamp", .06, .9, .07)], "overlay": "sparkles"},
    "stage": {"wall": (120, 60, 140), "floor": (200, 140, 90), "curtains": True, "lights": True,
              "props": [("drum", .9, .86, .1), ("bell", .08, .86, .07)], "overlay": "sparkles"},
}


def _grad(d, W, H, top, bot, y0=0, y1=None):
    y1 = y1 or H
    for y in range(int(y0), int(y1)):
        k = (y - y0) / max(1, y1 - y0)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(top, bot)))


def _hill(d, W, H, color, base, amp, freq, phase):
    pts = [(0, H)]
    for x in range(0, W + 20, 20):
        pts.append((x, base + math.sin(x / W * math.pi * freq + phase) * amp))
    pts.append((W, H))
    d.polygon(pts, fill=color)


def _prop(img, name, x, y, size, W, H):
    s = int(size * H)
    ic = icon(name, s)
    img.paste(ic, (int(x * W - s / 2), int(y * H - s / 2)), ic)


# AI-illustrated backgrounds for the episode being rendered: set id -> image path (render/aiart.py)
AI_BG: dict[str, str] = {}


def background(set_id: str, W: int, H: int, vivid: float = 1.0, calm: bool = False) -> Image.Image:
    """The graded set in the episode's art style (render/styles.py) and colour palette (render/palette.py); an AI
    illustration replaces the drawn set when one was generated for this episode."""
    from . import palette
    from .styles import CURRENT
    return _styled_bg(set_id, W, H, vivid, CURRENT["style"], AI_BG.get(set_id, ""), palette.wash(calm))


@lru_cache(maxsize=10)
def _styled_bg(set_id: str, W: int, H: int, vivid: float, style: str, ai: str = "",
               wash: tuple = (255, 247, 236)) -> Image.Image:
    from .styles import bg_fx
    img = _graded(set_id, W, H, vivid, ai, wash)
    return img if style == "classic" or ai else bg_fx(img, style)      # AI art is already painted in the style


def _ai_image(path: str, W: int, H: int) -> Image.Image | None:
    try:
        return Image.open(path).convert("RGB").resize((W, H), Image.LANCZOS)
    except Exception:  # noqa: BLE001
        return None


@lru_cache(maxsize=6)
def _graded(set_id: str, W: int, H: int, vivid: float = 1.0, ai: str = "", wash: tuple = (255, 247, 236)) -> Image.Image:
    """The set, colour-graded: vivid > 1 boosts saturation (the pace's colour energy), a warm grade, a soft
    sunlight glow on outdoor sets and a gentle depth haze toward the horizon."""
    from PIL import ImageChops, ImageEnhance
    img = (_ai_image(ai, W, H) if ai else None) or _background(set_id, W, H)
    spec = SETS.get(set_id) or SETS["meadow"]
    if vivid and abs(vivid - 1) > 0.01:
        img = ImageEnhance.Color(img).enhance(vivid)
        img = ImageEnhance.Contrast(img).enhance(1 + (vivid - 1) * 0.3)
    img = ImageChops.multiply(img, Image.new("RGB", (W, H), tuple(wash)))          # warm grade, tinted by the palette
    if "wall" not in spec and not spec.get("dark") and not spec.get("underwater"):
        glow = Image.radial_gradient("L").resize((int(W * 1.3), int(W * 1.3)))
        glow = glow.point(lambda v: int(max(0, 170 - v) / 170 * 110))      # fades to exactly 0 inside the square
        layer = Image.new("L", (W, H), 0)
        layer.paste(glow, (int(W * .88 - glow.width / 2), int(-H * .12 - glow.height / 2) + int(H * .1)))
        img.paste((255, 244, 210), (0, 0), layer)
        haze = Image.linear_gradient("L").resize((W, H)).point(lambda v: int(max(0, 70 - abs(v - 200) * 1.1)))
        img.paste(lighten(spec["sky"][1], .4), (0, 0), haze)
    return img


def background_blur(set_id: str, W: int, H: int, vivid: float = 1.0, calm: bool = False) -> Image.Image:
    """Lens blur for close-ups (depth of field)."""
    from . import palette
    from .styles import CURRENT
    return _blur_bg(set_id, W, H, vivid, CURRENT["style"], calm, palette.wash(calm))


@lru_cache(maxsize=6)
def _blur_bg(set_id: str, W: int, H: int, vivid: float, style: str, calm: bool = False, wash: tuple = ()) -> Image.Image:
    return background(set_id, W, H, vivid, calm).filter(ImageFilter.GaussianBlur(max(2, H // 160)))


@lru_cache(maxsize=10)
def _background(set_id: str, W: int, H: int) -> Image.Image:
    spec = SETS.get(set_id) or SETS["meadow"]
    img = Image.new("RGB", (W, H), (200, 230, 255))
    d = ImageDraw.Draw(img)
    rnd = random.Random(set_id)
    gy = H * GROUND
    lw = max(2, H // 300)
    if "wall" in spec:                                   # ---- indoor
        wall = spec["wall"]
        _grad(d, W, H, lighten(wall, .2), wall, 0, gy)
        for x in range(0, W, W // 16):                   # soft wallpaper stripes
            d.rectangle([x, 0, x + W // 32, gy], fill=lighten(wall, .08))
        d.rectangle([0, gy, W, H], fill=spec["floor"])
        for x in range(-H, W, H // 6):
            d.line([(x, H), (x + H * .4, gy)], fill=darken(spec["floor"], .06), width=lw)
        d.line([(0, gy), (W, gy)], fill=darken(wall, .3), width=lw * 2)
        if spec.get("window") or spec.get("window_night"):
            night = spec.get("window_night")
            wx, wy, ww, wh = W * .62, H * .1, W * .2, H * .32
            d.rounded_rectangle([wx, wy, wx + ww, wy + wh], 16, fill=(30, 40, 100) if night else (170, 220, 255),
                                outline=(255, 255, 255), width=lw * 4)
            d.line([(wx + ww / 2, wy), (wx + ww / 2, wy + wh)], fill=(255, 255, 255), width=lw * 3)
            d.line([(wx, wy + wh / 2), (wx + ww, wy + wh / 2)], fill=(255, 255, 255), width=lw * 3)
            if night:
                _prop(img, "moon", (wx + ww * .3) / W, (wy + wh * .3) / H, .08, W, H)
        if spec.get("board"):
            d.rounded_rectangle([W * .28, H * .1, W * .58, H * .46], 14, fill=(70, 140, 100), outline=(160, 110, 60), width=lw * 5)
        if spec.get("abc"):
            for i, ch in enumerate("ABCDEFGHIJ"):
                x = W * .03 + i * W * .095
                col = [(240, 90, 90), (255, 170, 60), (90, 190, 110), (90, 150, 240), (170, 110, 220)][i % 5]
                d.rounded_rectangle([x, H * .02, x + W * .07, H * .08], 8, fill=lighten(col, .3))
        if spec.get("bed"):
            d.rounded_rectangle([W * .58, H * .55, W * .98, H * .86], 30, fill=(255, 210, 120), outline=OUT, width=lw * 2)
            d.rounded_rectangle([W * .6, H * .5, W * .72, H * .6], 20, fill=(255, 255, 255), outline=OUT, width=lw * 2)
            d.rounded_rectangle([W * .66, H * .6, W * .98, H * .8], 30, fill=(150, 170, 240), outline=OUT, width=lw * 2)
        if spec.get("shelves"):
            for row in range(3):
                y = H * (.14 + row * .18)
                d.rectangle([W * .03, y + H * .12, W * .42, y + H * .14], fill=(150, 100, 60), outline=OUT, width=lw)
                x = W * .04
                while x < W * .4:
                    bw = W * rnd.uniform(.018, .03)
                    bh = H * rnd.uniform(.08, .115)
                    col = rnd.choice([(240, 90, 90), (90, 150, 240), (255, 200, 70), (110, 190, 110), (170, 120, 220)])
                    d.rectangle([x, y + H * .12 - bh, x + bw, y + H * .12], fill=col, outline=OUT, width=max(1, lw // 2))
                    x += bw + 2
        if spec.get("table"):
            d.rectangle([W * .62, H * .6, W * .98, H * .64], fill=(200, 160, 120), outline=OUT, width=lw * 2)
        if spec.get("flasks"):
            for i, col in enumerate([(255, 120, 150), (120, 200, 255), (150, 230, 120)]):
                x = W * (.68 + i * .1)
                d.ellipse([x - H * .04, H * .5, x + H * .04, H * .6], fill=col, outline=OUT, width=lw * 2)
                d.rectangle([x - H * .012, H * .44, x + H * .012, H * .51], fill=(240, 250, 255), outline=OUT, width=lw * 2)
        if spec.get("counter"):
            d.rectangle([W * .6, H * .6, W, gy], fill=(240, 240, 245), outline=OUT, width=lw * 2)
            d.rectangle([W * .6, H * .58, W, H * .61], fill=(200, 160, 120), outline=OUT, width=lw * 2)
        if spec.get("curtains"):
            for sx in (0, 1):
                x0 = 0 if sx == 0 else W * .86
                d.rectangle([x0, 0, x0 + W * .14, gy], fill=(200, 50, 70))
                for k in range(5):
                    xx = x0 + k * W * .028
                    d.line([(xx, 0), (xx, gy)], fill=(170, 35, 55), width=lw * 3)
            d.rectangle([0, 0, W, H * .08], fill=(200, 50, 70))
        if spec.get("lights"):
            spot = Image.new("L", (W, H), 0)
            ImageDraw.Draw(spot).ellipse([W * .25, H * .55, W * .75, H * 1.0], fill=90)
            spot = spot.filter(ImageFilter.GaussianBlur(H // 20))
            img.paste((255, 240, 180), (0, 0), spot)
    else:                                                # ---- outdoor
        top, bot = spec["sky"]
        _grad(d, W, H, top, bot, 0, gy if not spec.get("underwater") else H)
        if spec.get("map"):
            d.rectangle([0, 0, W, H], fill=(110, 185, 245))
            blobs = [(.18, .32, .12, .14), (.24, .62, .07, .16), (.47, .3, .06, .1), (.5, .58, .09, .16), (.68, .35, .17, .14),
                     (.82, .7, .08, .07), (.5, .93, .3, .04)]
            cols = [(140, 210, 120), (255, 200, 110), (170, 210, 130), (240, 190, 100), (150, 210, 140), (230, 170, 120), (245, 250, 255)]
            for (x, y, rx, ry), col in zip(blobs, cols):
                d.ellipse([W * (x - rx), H * (y - ry), W * (x + rx), H * (y + ry)], fill=col, outline=darken(col, .3), width=lw * 2)
        if spec.get("underwater"):
            for i in range(8):                            # light rays
                x = W * (i / 8 + .05)
                d.polygon([(x, 0), (x + W * .04, 0), (x + W * .12, H), (x + W * .06, H)], fill=lighten(top, .12))
            _hill(d, W, H, spec["ground"], H * .9, H * .02, 3, 1)
        if spec.get("dark"):
            for _ in range(140):
                x, y = rnd.random() * W, rnd.random() * gy * .9
                r = rnd.choice([1, 1, 2, 2, 3]) * H / 1080
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 220))
        if spec.get("volcano"):
            d.polygon([(W * .45, gy), (W * .62, H * .28), (W * .7, H * .28), (W * .9, gy)], fill=(150, 120, 110))
            d.polygon([(W * .62, H * .28), (W * .7, H * .28), (W * .68, H * .36), (W * .64, H * .35)], fill=(255, 150, 80))
        if spec.get("buildings"):
            for i in range(9):
                bw, bh = W * rnd.uniform(.07, .11), H * rnd.uniform(.25, .5)
                x = i * W / 9 + rnd.uniform(-10, 10)
                col = rnd.choice([(255, 200, 150), (180, 210, 240), (240, 170, 170), (200, 230, 180), (250, 230, 150)])
                d.rounded_rectangle([x, gy - bh, x + bw, gy], 10, fill=col, outline=darken(col, .25), width=lw * 2)
                for wy in range(int(gy - bh + 20), int(gy - 30), int(H * .07)):
                    for wx in (x + bw * .2, x + bw * .6):
                        d.rounded_rectangle([wx, wy, wx + bw * .2, wy + H * .035], 5, fill=(255, 250, 220))
        for k, col in enumerate(spec.get("hills", [])):
            _hill(d, W, H, col, gy - H * (.12 - k * .05), H * .04, 2 + k, k * 1.7)
        if spec.get("sea"):
            d.rectangle([0, gy - H * .12, W, gy], fill=spec["sea"])
            for x in range(0, W, W // 12):
                d.arc([x, gy - H * .14, x + W // 12, gy - H * .1], 200, 340, fill=(255, 255, 255), width=lw * 2)
        if "ground" in spec and not spec.get("underwater") and not spec.get("map"):
            if spec.get("moonground"):
                d.rectangle([0, gy, W, H], fill=spec["ground"])
                for _ in range(10):
                    x, r = rnd.random() * W, H * rnd.uniform(.015, .04)
                    y = gy + rnd.random() * (H - gy) * .8 + r
                    d.ellipse([x - r * 2, y - r, x + r * 2, y + r], fill=darken(spec["ground"], .15))
            else:
                _hill(d, W, H, spec["ground"], gy, H * .012, 1.5, 0.3)
                d.rectangle([0, gy + H * .015, W, H], fill=spec["ground"])
                for _ in range(60):                      # grass tufts / texture
                    x, y = rnd.random() * W, gy + H * .03 + rnd.random() * (H - gy - H * .03)
                    d.arc([x - 8, y - 6, x + 8, y + 6], 200, 340, fill=darken(spec["ground"], .1), width=lw)
        if spec.get("road"):
            d.rectangle([0, H * .88, W, H * .98], fill=(110, 110, 120))
            for x in range(0, W, W // 10):
                d.rectangle([x, H * .925, x + W // 20, H * .935], fill=(255, 230, 120))
        if spec.get("fence"):
            for x in range(0, W, W // 24):
                d.rounded_rectangle([x, gy - H * .07, x + W // 60, gy + H * .01], 4, fill=(255, 240, 220), outline=(180, 150, 120), width=lw)
            d.rectangle([0, gy - H * .05, W, gy - H * .04], fill=(255, 240, 220))
        if spec.get("slide"):
            d.line([(W * .78, gy - H * .32), (W * .95, gy)], fill=(255, 170, 60), width=int(H * .03))
            d.line([(W * .76, gy - H * .32), (W * .76, gy)], fill=(90, 150, 240), width=int(H * .012))
            d.rectangle([W * .74, gy - H * .34, W * .8, gy - H * .31], fill=(240, 90, 90))
        if spec.get("acacia"):
            for x0 in (.1, .82):
                d.line([(W * x0, gy), (W * x0, gy - H * .3)], fill=(140, 100, 70), width=int(H * .02))
                d.ellipse([W * (x0 - .1), gy - H * .4, W * (x0 + .1), gy - H * .28], fill=(130, 170, 80))
        if spec.get("vines"):
            for x in (.3, .45, .7):
                d.line([(W * x, 0), (W * x + 20, H * .25)], fill=(70, 140, 70), width=lw * 3)
        if spec.get("seaweed"):
            for x in (.05, .12, .9, .96):
                pts = [(W * x + math.sin(k * .6) * 20, H - k * H * .05) for k in range(8)]
                d.line(pts, fill=(70, 170, 100), width=int(H * .02), joint="curve")
        if spec.get("clouds_big"):
            for x, y, s in [(.2, .7, .3), (.75, .75, .35), (.5, .9, .4)]:
                _prop(img, "cloud", x, y, s, W, H)
    for name, x, y, s in spec.get("props", []):
        _prop(img, name, x, y, s, W, H)
    return img


# ---------------------------------------------------------------- living overlays
@lru_cache(maxsize=8)
def _particles(kind: str, W: int, H: int):
    rnd = random.Random(kind)
    if kind == "clouds":
        return [(rnd.random(), rnd.uniform(.05, .3), rnd.uniform(.12, .2), rnd.uniform(.004, .01)) for _ in range(4)]
    if kind in ("stars", "sparkles"):
        return [(rnd.random(), rnd.uniform(.03, .6), rnd.uniform(.015, .03), rnd.uniform(0, 6.28)) for _ in range(14)]
    if kind == "bubbles":
        return [(rnd.random(), rnd.random(), rnd.uniform(.01, .025), rnd.uniform(.03, .07)) for _ in range(18)]
    if kind == "snow":
        return [(rnd.random(), rnd.random(), rnd.uniform(.006, .012), rnd.uniform(.03, .06)) for _ in range(40)]
    if kind == "leaves":
        return [(rnd.random(), rnd.random(), rnd.uniform(.02, .035), rnd.uniform(.02, .04)) for _ in range(6)]
    return []


def overlay(frame: Image.Image, set_id: str, t: float, avoid: tuple[float, float] | None = None):
    """Moving set particles. `avoid` = (top, bottom) as fractions of the height: no clouds there (e.g. a title)."""
    kind = (SETS.get(set_id) or {}).get("overlay")
    if not kind:
        return
    W, H = frame.size
    d = ImageDraw.Draw(frame)
    for p in _particles(kind, W, H):
        if kind == "clouds":
            x0, y, s, v = p
            if avoid and y < avoid[1] and y + s > avoid[0]:
                continue
            x = ((x0 + t * v) % 1.3 - .15) * W
            ic = icon("cloud", int(s * H))
            frame.paste(ic, (int(x - ic.width / 2), int(y * H)), ic)
        elif kind in ("stars", "sparkles"):
            x, y, s, ph = p
            k = .5 + .5 * math.sin(t * 1.3 + ph)          # slow twinkle (well under 3 Hz)
            ic = icon("star", max(6, int(s * H * (.75 + .35 * k))))
            frame.paste(ic, (int(x * W - ic.width / 2), int(y * H - ic.height / 2)), ic)
        elif kind == "bubbles":
            x, y0, r, v = p
            y = (y0 - t * v) % 1.1
            xx = x * W + math.sin(t + x * 10) * 12
            rr = r * H
            d.ellipse([xx - rr, y * H - rr, xx + rr, y * H + rr], outline=(220, 240, 255), width=max(2, H // 400))
        elif kind == "snow":
            x, y0, r, v = p
            y = (y0 + t * v) % 1.05
            xx = x * W + math.sin(t * .8 + x * 20) * 15
            rr = r * H
            d.ellipse([xx - rr, y * H - rr, xx + rr, y * H + rr], fill=(255, 255, 255))
        elif kind == "leaves":
            x, y0, s, v = p
            y = (y0 + t * v) % 1.1
            ic = icon("leaf", int(s * H)).rotate(math.degrees(math.sin(t + x * 7)) * .5, expand=True)
            frame.paste(ic, (int(x * W + math.sin(t * .7 + x * 9) * 30), int(y * H)), ic)
