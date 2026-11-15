"""Art styles ("looks"). Same characters, same story — a different visual treatment.

Each look works on three levels, so it stays cheap at 1080p:
  sprite_fx  applied once per cached character pose          (free per frame)
  bg_fx      applied once per cached background               (free per frame)
  frame_fx   a light per-frame pass (grain, palette, tilt-shift…)
Stop-motion looks animate "on twos" (12 drawings a second) like real cut-out films.

Which looks attract which children (bands = where the optimizer may use the look on "auto"):
  paper cutout, comic — tactile, crafty: loved by 2-8s
  pixel art, retro anime — older kids (6-12); PS2 / risograph — grown-up nostalgia, older bands only
"""
from __future__ import annotations

import math
import random
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

ALL = ["toddler", "preschool", "early", "big"]
CURRENT = {"style": "classic"}          # the look of the episode being rendered (set by the Timeline)


def set_style(style: str | None) -> str:
    CURRENT["style"] = style if style in STYLES else "classic"
    return CURRENT["style"]
STYLES: dict[str, dict] = {
    "toy3d": {"label": "3D cartoon", "bands": ALL, "stepped": False, "engine": "3d",
              "note": "Real 3D (Blender): soft vinyl-toy characters with cartoon outlines, 3D sets with depth and "
                      "shadows. Slower to render: ~1-2 s a frame on CPU, much faster on an NVIDIA GPU."},
    "classic": {"label": "Classic cartoon", "bands": ALL, "stepped": False,
                "note": "Soft 3D-shaded picture-book cartoon (the channel's signature look)."},
    "paper": {"label": "Paper cutout", "bands": ALL, "stepped": True,
              "note": "Cut-paper characters with white edges and drop shadows on layered paper. Crafty, calm, very kid-friendly."},
    "comic": {"label": "Comic art", "bands": ["preschool", "early", "big"], "stepped": False,
              "note": "Bold ink outlines, halftone dots, punchy flat colour."},
    "pixel": {"label": "Pixel art", "bands": ["early", "big"], "stepped": False,
              "note": "Retro video-game pixels with a limited palette. Older kids love it."},
    "anime": {"label": "Retro anime", "bands": ["early", "big"], "stepped": False,
              "note": "Cel-shaded two-tone shadows, soft 90s palette and film grain."},
    "ps2": {"label": "PS2 style", "bands": ["big"], "stepped": False,
            "note": "Early-2000s console look: low-res, soft, a little fog. Mostly nostalgia, so big kids only."},
    "risograph": {"label": "Risograph", "bands": ["big"], "stepped": False,
                  "note": "Two-ink print look with grain and slight misregistration. An arty look for big kids."},
}


def get(style: str | None) -> dict:
    return {"id": style if style in STYLES else "classic", **STYLES.get(style or "", STYLES["classic"])}


def for_band(band: str) -> list[str]:
    return [k for k, v in STYLES.items() if band in v["bands"] and v.get("engine") != "3d"]   # auto never picks slow 3D


# ---------------------------------------------------------------- textures (cached)
@lru_cache(maxsize=8)
def _noise(w: int, h: int, seed: int, scale: int = 1) -> Image.Image:
    rnd = random.Random(seed)
    small = Image.frombytes("L", (max(1, w // scale), max(1, h // scale)),
                            bytes(rnd.randrange(256) for _ in range(max(1, w // scale) * max(1, h // scale))))
    return small.resize((w, h), Image.BILINEAR) if scale > 1 else small


@lru_cache(maxsize=4)
def _halftone(w: int, h: int, step: int) -> Image.Image:
    im = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(im)
    r = step * .28
    for y in range(0, h + step, step):
        off = step / 2 if (y // step) % 2 else 0
        for x in range(0, w + step, step):
            d.ellipse([x + off - r, y - r, x + off + r, y + r], fill=205)
    return im


def _alpha_outline(img: Image.Image, px: int, color) -> Image.Image:
    """A solid border of `px` around the sprite's shape (ink line, paper edge)."""
    a = img.getchannel("A")
    grown = a.filter(ImageFilter.MaxFilter(px * 2 + 1)) if px > 0 else a
    base = Image.new("RGBA", img.size, (*color, 0))
    base.putalpha(grown)
    base.alpha_composite(img)
    return base


def _pad(img: Image.Image, p: int) -> Image.Image:
    out = Image.new("RGBA", (img.width + 2 * p, img.height + 2 * p), (0, 0, 0, 0))
    out.paste(img, (p, p))
    return out


def _lowpoly(img: Image.Image, step: int) -> Image.Image:
    """Faceted triangles: each grid cell split in two, each triangle filled with its average colour."""
    w, h = img.size
    rgba = img.mode == "RGBA"
    src = img.convert("RGBA")
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    small = src.resize((max(1, w // step) * 2, max(1, h // step) * 2), Image.BOX)
    sp = small.load()
    for j in range(h // step + 1):
        for i in range(w // step + 1):
            x0, y0 = i * step, j * step
            for k, tri in enumerate((((x0, y0), (x0 + step, y0), (x0, y0 + step)),
                                     ((x0 + step, y0), (x0 + step, y0 + step), (x0, y0 + step)))):
                sx = min(small.width - 1, i * 2 + k)
                sy = min(small.height - 1, j * 2 + k)
                c = sp[sx, sy]
                if rgba and c[3] < 100:
                    continue
                shade = 1.06 if k == 0 else .92                      # flat facet lighting
                d.polygon(tri, fill=(min(255, int(c[0] * shade)), min(255, int(c[1] * shade)), min(255, int(c[2] * shade)), 255))
    if rgba:
        out.putalpha(ImageChops.multiply(out.getchannel("A"), img.getchannel("A").point(lambda v: 255 if v > 90 else 0)))
        return out
    return out.convert("RGB")


def _cel(img: Image.Image) -> Image.Image:
    """Two-tone cel shading: posterise light into hard bands."""
    rgb = img.convert("RGB")
    out = ImageOps.posterize(rgb, 3)
    out = ImageEnhance.Color(out).enhance(.9)
    if img.mode == "RGBA":
        out = out.convert("RGBA")
        out.putalpha(img.getchannel("A"))
    return out


# ---------------------------------------------------------------- per-asset effects (cached by callers)
def sprite_fx(img: Image.Image, style: str) -> Image.Image:
    if style in ("classic", "pixel", "risograph", "ps2") or img.width < 12:
        return img
    h = img.height
    if style == "comic":
        out = _alpha_outline(img, max(2, h // 70), (20, 15, 30))
        tone = _halftone(out.width, out.height, max(5, h // 45))
        rgb = ImageChops.multiply(out.convert("RGB"), Image.merge("RGB", (tone, tone, tone)))
        rgb = ImageEnhance.Color(rgb).enhance(1.2)
        res = rgb.convert("RGBA")
        res.putalpha(out.getchannel("A"))
        return res
    if style == "paper":
        p = max(3, h // 45)
        out = _alpha_outline(_pad(img, p * 2), p, (255, 253, 245))
        tex = _noise(out.width, out.height, 7, 3).point(lambda v: 225 + v // 9)
        rgb = ImageChops.multiply(out.convert("RGB"), Image.merge("RGB", (tex, tex, tex)))
        res = rgb.convert("RGBA")
        res.putalpha(out.getchannel("A"))
        shadow = Image.new("RGBA", res.size, (40, 30, 50, 0))
        shadow.putalpha(res.getchannel("A").filter(ImageFilter.GaussianBlur(p)).point(lambda v: int(v * .45)))
        final = Image.new("RGBA", (res.width + p * 2, res.height + p * 2), (0, 0, 0, 0))
        final.alpha_composite(shadow, (p * 2, p * 2))
        final.alpha_composite(res, (0, 0))
        return final.rotate(1.5, resample=Image.BICUBIC, expand=False)
    if style == "anime":
        # hard two-tone cel shadow on the lower-right of every shape + thin dark line
        a = img.getchannel("A")
        shifted = a.transform(img.size, Image.AFFINE, (1, 0, -h * .045, 0, 1, -h * .03))
        shadow = ImageChops.subtract(a, shifted).point(lambda v: 255 if v > 60 else 0)
        rgb = ImageEnhance.Color(img.convert("RGB")).enhance(.92)
        rgb = Image.composite(ImageChops.multiply(rgb, Image.new("RGB", img.size, (175, 165, 205))), rgb, shadow)
        res = rgb.convert("RGBA")
        res.putalpha(a)
        return _alpha_outline(res, max(1, h // 150), (45, 30, 55))
    return img


def bg_fx(img: Image.Image, style: str) -> Image.Image:
    if style in ("classic", "pixel", "risograph"):
        return img
    w, h = img.size
    if style == "comic":
        edges = img.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda v: 0 if v > 40 else 255)
        tone = _halftone(w, h, max(6, h // 90))
        out = ImageChops.multiply(ImageEnhance.Color(img).enhance(1.25), Image.merge("RGB", (tone, tone, tone)))
        return ImageChops.multiply(out, Image.merge("RGB", (edges, edges, edges)))
    if style == "paper":
        out = ImageOps.posterize(img, 4)
        tex = _noise(w, h, 11, 4).point(lambda v: 222 + v // 8)
        out = ImageChops.multiply(out, Image.merge("RGB", (tex, tex, tex)))
        edges = out.convert("L").filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(2)).point(lambda v: 255 - min(90, v))
        return ImageChops.multiply(out, Image.merge("RGB", (edges, edges, edges)))
    if style == "anime":
        return ImageEnhance.Color(_cel(img).convert("RGB")).enhance(.85)
    if style == "ps2":
        return _lowpoly(img, max(12, h // 18))
    return img


# ---------------------------------------------------------------- per-frame pass
@lru_cache(maxsize=4)
def _tilt_mask(w: int, h: int) -> Image.Image:
    g = Image.linear_gradient("L").resize((w, h))
    return g.point(lambda v: int(min(255, max(0, abs(v - 150) - 45) * 2.6)))


PIXEL_PALETTE = None


def frame_fx(f: Image.Image, style: str, t: float) -> Image.Image:
    if style in ("classic", "comic", "paper"):
        if style == "paper":                            # film grain for the stop-motion feel
            g = _noise(f.width // 2, f.height // 2, int(t * 12) % 4, 1).resize(f.size, Image.NEAREST)
            f.paste((255, 255, 255), (0, 0), g.point(lambda v: 10 if v > 245 else 0))
        return f
    w, h = f.size
    if style == "pixel":
        small = f.resize((320, int(320 * h / w)), Image.BOX)
        small = small.quantize(colors=64, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).convert("RGB")
        return small.resize((w, h), Image.NEAREST)
    if style == "ps2":
        low = f.resize((640, int(640 * h / w)), Image.BILINEAR)
        low = ImageEnhance.Color(low).enhance(.85)
        out = low.resize((w, h), Image.BILINEAR)
        fog = Image.linear_gradient("L").rotate(180).resize((w, h)).point(lambda v: int(v * .18))
        out.paste((200, 205, 225), (0, 0), fog)
        return out
    if style == "anime":
        g = _noise(w // 2, h // 2, int(t * 24) % 4, 1).resize((w, h), Image.NEAREST)
        f.paste((255, 250, 240), (0, 0), g.point(lambda v: 14 if v > 240 else 0))
        return f
    if style == "risograph":
        lum = ImageOps.autocontrast(f.convert("L"))
        pink = ImageOps.colorize(lum, (255, 72, 176), (255, 248, 240))
        blue = ImageOps.colorize(lum, (0, 120, 191), (255, 248, 240))
        blue = ImageChops.offset(blue, max(2, w // 400), max(1, h // 500))     # misregistration
        out = ImageChops.multiply(pink, blue)
        g = _noise(w // 2, h // 2, int(t * 12) % 3, 1).resize((w, h), Image.NEAREST)
        out.paste((255, 250, 240), (0, 0), g.point(lambda v: 40 if v > 230 else 0))
        return out
    return f


def step_time(t: float, style: str) -> float:
    """Stop-motion looks move 12 times a second (animated 'on twos')."""
    return math.floor(t * 12) / 12 if STYLES.get(style, {}).get("stepped") else t
