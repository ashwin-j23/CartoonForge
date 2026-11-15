"""Shared drawing helpers. Everything is drawn supersampled (SS x) and scaled down = smooth, anti-aliased edges."""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .. import config

SS = 3                      # supersampling factor for sprites
OUT = (45, 40, 70)          # soft dark-plum outline (gentler than black for young eyes)
WHITE = (255, 255, 255)

COLORS = {
    "red": (240, 70, 70), "orange": (255, 150, 50), "yellow": (255, 215, 60), "green": (90, 195, 95),
    "blue": (70, 140, 235), "purple": (155, 105, 215), "pink": (255, 140, 190), "brown": (160, 105, 65),
    "black": (50, 50, 60), "white": (250, 250, 250), "gray": (160, 165, 175), "grey": (160, 165, 175),
}
COLOR_NAMES = {"red": "Red", "orange": "Orange", "yellow": "Yellow", "green": "Green", "blue": "Blue",
               "purple": "Purple", "pink": "Pink", "brown": "Brown", "black": "Black", "white": "White"}


@lru_cache(maxsize=64)
def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(config.FONTS / "Fredoka.ttf"), max(8, int(size)))
    try:
        f.set_variation_by_name(weight)
    except Exception:  # noqa: BLE001
        pass
    return f


def ease_out_back(x: float, s: float = 1.7) -> float:
    x = max(0.0, min(1.0, x)) - 1
    return x * x * ((s + 1) * x + s) + 1


def ease_in_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


def ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def canvas(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (int(w * SS), int(h * SS)), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def finish(im: Image.Image) -> Image.Image:
    return im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)


def ell(d: ImageDraw.ImageDraw, cx, cy, rx, ry, fill, outline=OUT, w=0):
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill, outline=outline if w else None, width=int(w))


def lighten(c, k=0.35):
    return tuple(int(v + (255 - v) * k) for v in c[:3])


def darken(c, k=0.25):
    return tuple(int(v * (1 - k)) for v in c[:3])


def paste(base: Image.Image, img: Image.Image, cx: float, cy: float, alpha: float = 1.0):
    """Alpha-composite img centred at (cx, cy)."""
    if alpha <= 0.01:
        return
    if alpha < 0.99:
        img = img.copy()
        a = img.getchannel("A").point(lambda v: int(v * alpha))
        img.putalpha(a)
    base.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2))) if base.mode == "RGBA" else \
        base.paste(img, (int(cx - img.width / 2), int(cy - img.height / 2)), img)


def rounded(w: int, h: int, r: int, fill, outline=None, width=0) -> Image.Image:
    im, d = canvas(w, h)
    d.rounded_rectangle([width * SS, width * SS, w * SS - 1 - width * SS, h * SS - 1 - width * SS], r * SS, fill=fill,
                        outline=outline, width=int(width * SS))
    return finish(im)


def text_img(text: str, size: int, fill=WHITE, stroke=OUT, stroke_w: float = 0.12, weight="Bold") -> Image.Image:
    f = font(size, weight)
    sw = max(1, int(size * stroke_w)) if stroke else 0
    box = f.getbbox(text, stroke_width=sw)
    im = Image.new("RGBA", (box[2] - box[0] + 4, box[3] - box[1] + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - box[0], 2 - box[1]), text, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke)
    return im


def fit_text(text: str, max_w: int, start: int, minimum: int = 28, **kw) -> Image.Image:
    size = start
    while size > minimum:
        im = text_img(text, size, **kw)
        if im.width <= max_w:
            return im
        size = int(size * 0.9)
    return text_img(text, minimum, **kw)
