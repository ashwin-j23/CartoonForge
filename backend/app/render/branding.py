"""YouTube channel art: profile picture (800x800, circle-safe) and banner (2560x1440, safe-area aware).

    python -m app.render.branding OUT_DIR [--name "Hoppy Hop Hop"] [--tagline "..."]

Banner zones (YouTube): the whole 2560x1440 shows on TVs; desktop shows the middle 2560x423 strip; phones and
the "safe area" show only the centre 1546x423. Name, tagline and Hoppy stay inside the safe area; the friends
sit in the desktop-only side zones.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import palette, sets
from .characters import shadow, sprite
from .common import OUT, rounded, text_img

BW, BH = 2560, 1440
SAFE = (507, 508, 2053, 931)                    # x0, y0, x1, y1 of the 1546x423 safe area
BAND = (0, 508, 2560, 931)                      # what desktop shows
PALETTE = "rainbow_playground"
TAGLINE = "Songs, stories & smiles for little learners!"


def _setup():
    from .styles import set_style
    set_style("classic")
    palette.set_current(PALETTE, "preschool")


def _title(name: str, size: int) -> Image.Image:
    """The channel name in the intro's colourful bouncy letters, slightly tilted for fun."""
    letters = [(text_img(ch, size, fill=palette.accent(i), stroke=(255, 255, 255), stroke_w=.14) if ch != " " else None)
               for i, ch in enumerate(name)]
    gap = int(size * .32)
    w = sum(im.width if im else gap for im in letters)
    h = max(im.height for im in letters if im) + int(size * .25)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for i, im in enumerate(letters):
        if im is None:
            x += gap
            continue
        rot = im.rotate(((i * 37) % 9 - 4) * 1.2, resample=Image.BICUBIC, expand=True)
        y = int(size * .12 + math.sin(i * 1.3) * size * .06)
        out.alpha_composite(rot, (x - (rot.width - im.width) // 2, y))
        x += im.width
    return out


def _drop_shadow(im: Image.Image, blur: int, offset: tuple[int, int], alpha: int = 90) -> Image.Image:
    pad = blur * 3
    sh = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: v * alpha // 255)
    sh.paste((40, 30, 80, 255), (pad + offset[0], pad + offset[1]), a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh.alpha_composite(im, (pad, pad))
    return sh


def _pill(text: str, size: int) -> Image.Image:
    ti = text_img(text, size, fill=(255, 255, 255), stroke=OUT, stroke_w=.1)
    pill = rounded(ti.width + size * 2, int(size * 1.75), int(size * .87), palette.button(), outline=(255, 255, 255),
                   width=max(4, size // 9))
    pill.alpha_composite(ti, ((pill.width - ti.width) // 2, (pill.height - ti.height) // 2))
    return pill


def _hide_trunks(im: Image.Image, y0: int, y1: int) -> None:
    """Replace tree-trunk brown in a strip with the grass next to it (the set's trees end under the characters)."""
    import numpy as np
    px = np.asarray(im).copy()
    s = px[y0:y1].astype(int)
    r, g, b = s[..., 0], s[..., 1], s[..., 2]
    trunk = (r > g + 8) & (b < g)                                 # grass is always greener than red
    cols = np.where(trunk.any(axis=0))[0]
    if len(cols):
        for grp in np.split(cols, np.where(np.diff(cols) > 6)[0] + 1):
            a, z = int(grp[0]) - 6, int(grp[-1]) + 6                 # include the dark outline
            w = z - a
            src = z + 4 if z + 4 + w < im.width else a - 4 - w      # grass just beside the trunk
            px[y0:y1, a:z] = px[y0:y1, src:src + w]
        im.paste(Image.fromarray(px), (0, 0))


def banner(out: Path, name: str = "Hoppy Hop Hop", tagline: str = TAGLINE) -> Path:
    _setup()
    canvas = Image.new("RGBA", (BW, BH))
    # the meadow drawn for the desktop band, then sky above / grass below extended for TV view
    band_h = 640
    bg = sets.background("meadow", BW, band_h, palette.vivid_cap("preschool")).convert("RGBA")
    top, bottom = bg.crop((0, 0, BW, 1)), bg.crop((0, band_h - 1, BW, band_h))
    top_y = 400
    canvas.paste(top.resize((BW, top_y)), (0, 0))
    canvas.paste(bottom.resize((BW, BH - top_y - band_h)), (0, top_y + band_h))
    canvas.alpha_composite(bg, (0, top_y))
    ground = SAFE[3] - 22
    clean_y = ground + 3                                     # under the characters' feet: plain grass only (the
    grass = bottom.resize((BW, top_y + band_h - clean_y))                       # set's tree trunks poked out here)
    fade = Image.linear_gradient("L").resize((BW, 40))                          # soft seam, no hard line
    mask = Image.new("L", grass.size, 255)
    mask.paste(fade, (0, 0))
    _hide_trunks(canvas, clean_y - 60, clean_y + 45)
    canvas.paste(grass, (0, clean_y), mask)

    # TV-only sky: Sunny and a few clouds; TV-only grass: flowers
    from .icons import icon
    sun = sprite("sunny", 300, 1, "open", "happy", "down")
    canvas.alpha_composite(sun, (2560 - sun.width - 160, 90))
    for x, y, sz in ((260, 140, 150), (820, 260, 110), (1450, 120, 170), (1900, 300, 120), (560, 380, 90)):
        cl = icon("cloud", sz)
        canvas.alpha_composite(cl, (x, y))
    for x, y in ((180, 1120), (640, 1260), (1150, 1090), (1700, 1230), (2250, 1110), (2450, 1300), (980, 1350)):
        fl = icon("flower", 60)
        canvas.alpha_composite(fl, (x, y))

    # friends in the desktop-only side zones (decor), all standing on the grass line
    for cid, x, h, arms in (("pip", 95, 250, "up"), ("mimi", 265, 275, "wave"), ("nana", 430, 245, "wave"),
                            ("bo", 2150, 290, "wave"), ("zuzu", 2335, 265, "up")):
        sp = sprite(cid, h, 1, "open", "excited", arms)
        sh = shadow(int(sp.width * .7))
        canvas.alpha_composite(sh, (int(x - sh.width / 2), int(ground - sh.height / 2)))
        canvas.alpha_composite(sp, (int(x - sp.width / 2), int(ground - sp.height)))

    # Hoppy mid-hop on the left of the safe area, fully inside it (phones crop to the safe area)
    hp = sprite("hoppy", 340, 2, "open", "excited", "up")
    hp = _drop_shadow(hp, 10, (0, 8), 50)
    hx = SAFE[0] + 200
    top_room = SAFE[1] + 12
    hy = max(top_room, int(ground - hp.height - 25))
    sh = shadow(int(hp.width * .45))
    canvas.alpha_composite(sh, (int(hx - sh.width / 2), int(ground - sh.height / 2)))
    canvas.alpha_composite(hp, (int(hx - hp.width / 2), hy))

    # name + tagline, centred in the remaining safe area
    area_x0, area_x1 = SAFE[0] + 400, SAFE[2] - 20
    title = _title(name, 150)
    if title.width > area_x1 - area_x0:
        title = title.resize((area_x1 - area_x0, int(title.height * (area_x1 - area_x0) / title.width)), Image.LANCZOS)
    title = _drop_shadow(title, 8, (0, 6), 70)
    pill = _pill(tagline, 44)
    cx = (area_x0 + area_x1) // 2
    ty = SAFE[1] + 40
    canvas.alpha_composite(title, (cx - title.width // 2, ty))
    canvas.alpha_composite(pill, (cx - pill.width // 2, ty + title.height - 10))

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out


def avatar(out: Path, size: int = 800) -> Path:
    """Hoppy's big happy face on a bright sunburst: reads at 48 px, nothing important near the corners."""
    _setup()
    s = size * 2                                                     # draw at 2x, downscale for smooth edges
    im = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(im)
    cx = cy = s // 2
    c1, c2 = (255, 214, 92), (255, 168, 64)                          # warm sunburst rays
    for k in range(24):
        a0, a1 = k * 15, k * 15 + 15
        d.pieslice([-s, -s, 2 * s, 2 * s], a0, a1, fill=c1 if k % 2 else c2)
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([s * .14, s * .14, s * .86, s * .86], fill=(110, 205, 250, 255))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s // 60)))
    ImageDraw.Draw(im).ellipse([s * .16, s * .16, s * .84, s * .84], outline=(255, 255, 255), width=s // 60)
    hp = sprite("hoppy", int(s * .78), 2, "open", "excited", "up")
    hp = _drop_shadow(hp, s // 80, (0, s // 100), 60)
    im.alpha_composite(hp, (cx - hp.width // 2, int(cy - hp.height * .47)))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.resize((size, size), Image.LANCZOS).convert("RGB").save(out, "PNG", optimize=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--name", default="Hoppy Hop Hop")
    ap.add_argument("--tagline", default=TAGLINE)
    a = ap.parse_args()
    d = Path(a.out_dir)
    print(banner(d / "banner-2560x1440.png", a.name, a.tagline))
    print(avatar(d / "profile-800x800.png"))


if __name__ == "__main__":
    main()
