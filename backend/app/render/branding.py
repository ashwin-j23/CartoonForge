"""Hoppy Hop Hop brand kit: logo lockup, YouTube banner, profile picture and video watermark.

    python -m app.render.branding OUT_DIR

One strict palette (navy outline + seven brights), one logo treatment (bubbly Fredoka letters with a thick navy
outline, white rim, 3D extrusion and gloss), the same cast as the episodes.

Banner zones (YouTube 2560x1440): TVs show everything; desktop shows the 2560x423 middle strip; phones show
only the centre 1546x423 "safe area". Logo, ribbon and Hoppy stay in the safe area; friend groups sit in the
desktop-only sides; the TV-only sky/meadow carry the rainbow, rays and clouds.
"""
from __future__ import annotations

import argparse
import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import palette
from .characters import sprite
from .common import font

# ---------------------------------------------------------------- brand palette
NAVY = (31, 41, 96)
NAVY_DEEP = (20, 26, 66)
WHITE = (255, 255, 255)
GREEN = (78, 200, 92)
YELLOW = (255, 204, 38)
ORANGE = (255, 143, 38)
CORAL = (255, 86, 98)
BLUE = (44, 150, 255)
PURPLE = (150, 96, 235)
PINK = (255, 104, 178)
SKY_TOP, SKY_LOW = (36, 140, 236), (178, 228, 255)

BW, BH = 2560, 1440
SAFE = (507, 508, 2053, 931)
BAND = (0, 508, 2560, 931)
NAME = "Hoppy Hop Hop"
RIBBON = "New cartoons every day!"


def _setup():
    from .styles import set_style
    set_style("classic")
    palette.set_current("rainbow_playground", "preschool")


def _mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _vgrad(w, h, top, bottom):
    g = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), bottom), Image.new("RGB", (w, h), top), g).convert("RGBA")


# ---------------------------------------------------------------- logo lockup
def _glyph(ch: str, size: int, color, tilt: float) -> Image.Image:
    """One logo letter: navy extrusion, navy outline, white rim, colour fill with a top gloss."""
    f = font(size, "Bold")
    o, rim, depth = int(size * .17), int(size * .085), int(size * .10)
    pad = o + depth + 8
    box = f.getbbox(ch, stroke_width=o)
    w, h = box[2] - box[0] + pad * 2, box[3] - box[1] + pad * 2
    org = (pad - box[0], pad - box[1])

    def mask(stroke):
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text(org, ch, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
        return m

    m_out, m_rim, m_fill = mask(o), mask(rim), mask(0)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for k in range(depth, 0, -1):                                   # 3D extrusion
        im.paste(NAVY_DEEP + (255,), (0, k), m_out)
    im.paste(NAVY + (255,), (0, 0), m_out)
    im.paste(WHITE + (255,), (0, 0), m_rim)
    fill = _vgrad(w, h, _mix(color, WHITE, .28), _mix(color, (0, 0, 0), .12))
    im.paste(fill, (0, 0), m_fill)
    yb = m_fill.getbbox() or (0, 0, w, h)                            # gloss: light band on the top 38%
    gl = Image.new("L", (w, h), 0)
    ImageDraw.Draw(gl).rounded_rectangle([yb[0] + size * .08, yb[1] + size * .05, yb[2] - size * .08,
                                          yb[1] + (yb[3] - yb[1]) * .38], radius=int(size * .12), fill=110)
    gl = ImageChops.multiply(gl.filter(ImageFilter.GaussianBlur(size // 40)), m_fill)
    im.paste(WHITE + (255,), (0, 0), gl)
    return im.rotate(tilt, resample=Image.BICUBIC, expand=True)


BRAND_COLORS = (GREEN, YELLOW, CORAL, BLUE, ORANGE, PURPLE, PINK)


@lru_cache(maxsize=32)
def brand_letters(name: str, size: int) -> tuple:
    """The channel name as logo letters (same look as the banner logo), one image per character, None for spaces.
    Cached: the intro and every episode's title card draw these on every frame."""
    rnd = random.Random(name)
    out = []
    for i, ch in enumerate(name):
        if ch == " ":
            out.append(None)
            continue
        g = _glyph(ch, size, BRAND_COLORS[i % len(BRAND_COLORS)], rnd.uniform(-6, 6))
        out.append(g.crop(g.getchannel("A").getbbox()))
    return tuple(out)


def _word_line(text: str, size: int, colors, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    glyphs, x = [], 0
    track = -int(size * .09)                                          # letters overlap: one chunky word
    for i, ch in enumerate(text):
        if ch == " ":
            x += int(size * .16)
            continue
        g = _glyph(ch, size, colors[i % len(colors)], rnd.uniform(-7, 7))
        g = g.crop(g.getchannel("A").getbbox())
        glyphs.append((g, x, int(math.sin(i * 1.7 + seed) * size * .06)))
        x += g.width + track
    w = x - track + 4
    h = max(g.height for g, _, _ in glyphs) + int(size * .16)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for g, gx, dy in glyphs:
        out.alpha_composite(g, (gx, int(size * .08) + dy + (h - int(size * .16) - g.height) // 2))
    return out


def logo(width: int) -> Image.Image:
    """'Hoppy' over 'Hop Hop', stacked and overlapping like a toy-box logo."""
    top = _word_line("Hoppy", 300, [GREEN, YELLOW, CORAL, BLUE, ORANGE], 1)
    bot = _word_line("Hop Hop", 215, [PURPLE, PINK, GREEN, BLUE, YELLOW, CORAL], 4)
    overlap = int(top.height * .26)
    w = max(top.width, bot.width)
    out = Image.new("RGBA", (w, top.height + bot.height - overlap), (0, 0, 0, 0))
    out.alpha_composite(bot, ((w - bot.width) // 2 + int(w * .04), top.height - overlap))
    out.alpha_composite(top, ((w - top.width) // 2 - int(w * .02), 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))                  # soft drop shadow for lift
    sh.paste(NAVY_DEEP + (110,), (0, 0), out.getchannel("A"))
    pad = 40
    res = Image.new("RGBA", (out.width + pad * 2, out.height + pad * 2), (0, 0, 0, 0))
    res.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)), (pad + 6, pad + 18))
    res.alpha_composite(out, (pad, pad))
    return res.resize((width, int(res.height * width / res.width)), Image.LANCZOS)


# ---------------------------------------------------------------- scene pieces (drawn at 2x, downscaled)
def _rays(d: ImageDraw.ImageDraw, cx, cy, n, alpha, reach):
    for k in range(n):
        a0 = k * 360 / n
        a1 = a0 + 360 / n / 2
        p = [(cx, cy)] + [(cx + reach * math.cos(math.radians(a)), cy + reach * math.sin(math.radians(a)))
                          for a in (a0, a1)]
        d.polygon(p, fill=(255, 255, 255, alpha))


def _rainbow(size, cx, cy, r, band):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cols = [CORAL, ORANGE, YELLOW, GREEN, BLUE, PURPLE]
    d.ellipse([cx - r - band * .6, cy - r - band * .6, cx + r + band * .6, cy + r + band * .6], fill=WHITE + (150,))
    for i, c in enumerate(cols):
        rr = r - i * band
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=c + (255,))
    rr = r - len(cols) * band
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(0, 0, 0, 0))
    return im


def _cloud(w: int, seed: int) -> Image.Image:
    """A fluffy cartoon cloud: a flat-bottomed base plus three round puffs, all inside the canvas."""
    rnd = random.Random(seed)
    h = int(w * .6)
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([w * .06, h * .5, w * .94, h * .94], radius=int(h * .22), fill=255)
    for cx, cy, r in ((.3, .58, .2), (.54, .44, .27), (.76, .6, .18)):
        r *= w * rnd.uniform(.93, 1.05)
        x, y = cx * w, cy * h
        d.ellipse([x - r, max(1, y - r), x + r, y + r], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(w / 220))
    body = _vgrad(w, h, WHITE, (205, 230, 252))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(body, (0, 0), m)
    return out


def _hill(size, base_y, amp, waves, phase, color, rim):
    w, h = size
    pts = [(x, base_y + sum(a * math.sin(x / w * math.pi * 2 * f + phase * (j + 1))
                            for j, (a, f) in enumerate(zip(amp, waves)))) for x in range(0, w + 8, 8)]
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon(pts + [(w, h), (0, h)], fill=color + (255,))
    d.line(pts, fill=rim + (255,), width=10)
    shade = Image.linear_gradient("L").resize((w, h)).point(lambda v: int(v * .18))
    im.paste((0, 0, 0, 255), (0, 0), ImageChops.multiply(shade, im.getchannel("A")))
    return im


def _star(size, color):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c = size / 2
    pts = []
    for i in range(8):
        a = i * math.pi / 4 - math.pi / 2
        r = c if i % 2 == 0 else c * .3
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    ImageDraw.Draw(im).polygon(pts, fill=color + (255,))
    return im


def _shadow(w, h, alpha=70):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([0, 0, w - 1, h - 1], fill=NAVY_DEEP + (alpha,))
    return im.filter(ImageFilter.GaussianBlur(h / 4))


def _ribbon(text: str, size: int, color=CORAL) -> Image.Image:
    """A banner ribbon with folded tails behind, like a sticker label."""
    f = font(size, "Bold")
    sw = int(size * .1)
    tb = f.getbbox(text, stroke_width=sw)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    w, h = tw + size * 2, int(size * 1.7)
    tail = int(h * .55)
    im = Image.new("RGBA", (w + tail * 2 + 20, h + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0 = tail + 10, 6
    dark = _mix(color, NAVY_DEEP, .45)
    for side in (-1, 1):
        bx = x0 - tail * .75 if side < 0 else x0 + w - tail * .25
        top_y, bot_y = y0 + h * .3, y0 + h * 1.15
        if side < 0:
            pts = [(bx, top_y), (bx + tail, top_y), (bx + tail, bot_y), (bx, bot_y), (bx + tail * .35, y0 + h * .72)]
        else:
            pts = [(bx, top_y), (bx + tail, top_y), (bx + tail * .65, y0 + h * .72), (bx + tail, bot_y), (bx, bot_y)]
        d.polygon(pts, fill=dark + (255,), outline=NAVY + (255,), width=6)
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=int(h * .28), fill=color + (255,), outline=NAVY + (255,),
                        width=8)
    d.rounded_rectangle([x0 + 10, y0 + 8, x0 + w - 10, y0 + h * .42], radius=int(h * .2),
                        fill=_mix(color, WHITE, .3) + (255,))
    d.text((x0 + (w - tw) / 2 - tb[0], y0 + (h - th) / 2 - tb[1]), text, font=f, fill=WHITE,
           stroke_width=sw, stroke_fill=NAVY)
    return im


def _char(cid, h, mouth=1, emotion="excited", arms="wave", flip=False):
    sp = sprite(cid, h, mouth, "open", emotion, arms)
    return sp.transpose(Image.FLIP_LEFT_RIGHT) if flip else sp


def _stand(canvas, sp, x, gy, shadow_alpha=70):
    canvas.alpha_composite(_shadow(int(sp.width * .8), 30, shadow_alpha), (int(x - sp.width * .4), gy - 16))
    canvas.alpha_composite(sp, (int(x - sp.width / 2), gy - sp.height))


# ---------------------------------------------------------------- banner
def banner(out: Path, ribbon: str = RIBBON) -> Path:
    _setup()
    S = 2                                                             # supersample the drawn scenery
    W2, H2 = BW * S, BH * S
    sc = _vgrad(W2, H2, SKY_TOP, SKY_LOW)
    lx, ly = 1500, 700                                                # logo centre (1x)
    rays = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    _rays(ImageDraw.Draw(rays), lx * S, ly * S, 28, 26, W2)
    sc.alpha_composite(rays.filter(ImageFilter.GaussianBlur(6)))
    glow = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([(lx - 520) * S, (ly - 360) * S, (lx + 520) * S, (ly + 360) * S],
                                 fill=(255, 255, 230, 120))
    sc.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
    sc.alpha_composite(_rainbow((W2, H2), lx * S, 1010 * S, 640 * S, 30 * S))
    for x, y, w, seed in ((60, 330, 340, 1), (820, 240, 300, 2), (1240, 70, 380, 3), (1800, 230, 420, 4),
                          (2330, 420, 240, 5)):
        sc.alpha_composite(_cloud(w * S, seed), (x * S, y * S))
    for base, amp, wv, ph, col, rim in ((830, (48, 22), (1.4, 3.3), .4, (162, 226, 120), (205, 244, 165)),
                                        (880, (36, 16), (1.1, 2.6), 1.7, (112, 204, 96), (160, 232, 128)),
                                        (930, (22, 10), (.9, 2.1), 2.9, (74, 180, 80), (124, 214, 108))):
        sc.alpha_composite(_hill((W2, H2), base * S, tuple(a * S for a in amp), wv, ph, col, rim))
    rnd = random.Random(7)                                           # TV-only meadow: flowers
    d = ImageDraw.Draw(sc)
    for _ in range(70):
        x, y = rnd.uniform(0, W2), rnd.uniform(990 * S, H2 - 20)
        r = rnd.uniform(5, 9) * S
        c = rnd.choice([WHITE, YELLOW, PINK, CORAL])
        for k in range(5):
            a = k * 2 * math.pi / 5
            d.ellipse([x + math.cos(a) * r - r * .7, y + math.sin(a) * r - r * .7,
                       x + math.cos(a) * r + r * .7, y + math.sin(a) * r + r * .7], fill=c + (255,))
        d.ellipse([x - r * .6, y - r * .6, x + r * .6, y + r * .6], fill=(ORANGE if c == YELLOW else YELLOW) + (255,))
    canvas = sc.resize((BW, BH), Image.LANCZOS)

    ground = 920
    # left friends (desktop sides): Pip + Mimi; Nana Owl rides a little cloud in the TV sky
    _stand(canvas, _char("pip", 255, 1, "excited", "up"), 150, ground)
    _stand(canvas, _char("mimi", 290, 1, "excited", "wave"), 370, ground + 4)
    seat = _cloud(300, 11)
    nana = _char("nana", 210, 1, "happy", "wave")
    canvas.alpha_composite(nana, (330 + (seat.width - nana.width) // 2, 170))
    canvas.alpha_composite(seat, (330, 170 + nana.height - int(seat.height * .45)))
    # right friends: Bo + Zuzu facing in; Sunny high in the TV sky
    sun = _char("sunny", 300, 1, "happy", "down")
    canvas.alpha_composite(sun, (2170, 150))
    _stand(canvas, _char("bo", 320, 1, "excited", "wave", True), 2200, ground + 2)
    _stand(canvas, _char("zuzu", 280, 1, "excited", "up", True), 2410, ground)

    # Hoppy: the hero, mid-jump, big, inside the safe area, with motion lines under him
    hp = _char("hoppy", 395, 2, "excited", "up")
    hx, hy = 745, SAFE[1] + 6
    canvas.alpha_composite(_shadow(int(hp.width * .62), 34, 80), (int(hx - hp.width * .31), ground - 20))
    canvas.alpha_composite(hp, (int(hx - hp.width / 2), hy))

    # logo + ribbon (safe area, right of Hoppy), sparkles around
    rb = _ribbon(ribbon, 46)
    lg = logo(1100)
    room_h = SAFE[3] - SAFE[1] - rb.height + 36                       # logo + ribbon fill the safe height
    if lg.height > room_h:
        lg = lg.resize((int(lg.width * room_h / lg.height), room_h), Image.LANCZOS)
    canvas.alpha_composite(lg, (lx - lg.width // 2, SAFE[1] - 8))
    canvas.alpha_composite(rb, (lx - rb.width // 2 + 20, SAFE[3] - rb.height - 2))
    for x, y, s, c in ((960, 560, 46, YELLOW), (2010, 600, 38, WHITE), (1000, 860, 30, WHITE),
                       (1990, 820, 44, YELLOW), (1180, 540, 26, WHITE), (1830, 900, 26, PINK)):
        canvas.alpha_composite(_star(s, c), (x - s // 2, y - s // 2))

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out


# ---------------------------------------------------------------- profile picture + watermark
def avatar(out: Path, size: int = 800) -> Path:
    """Hoppy's face, big and happy, on a clean warm radial background: reads instantly at 40 px."""
    _setup()
    s = size * 2
    bg = Image.new("RGBA", (s, s))
    r = Image.radial_gradient("L").resize((s, s))
    bg.paste(Image.composite(Image.new("RGB", (s, s), (255, 150, 30)), Image.new("RGB", (s, s), (255, 226, 92)),
                             r).convert("RGBA"))
    rays = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    _rays(ImageDraw.Draw(rays), s / 2, s * .46, 20, 34, s)
    bg.alpha_composite(rays.filter(ImageFilter.GaussianBlur(4)))
    full = sprite("hoppy", int(s * 1.55), 2, "open", "excited", "down")
    bb = full.getbbox()
    head = full.crop((bb[0], bb[1], bb[2], bb[1] + int((bb[3] - bb[1]) * .86)))   # head, scarf, body
    hw = int(s * .8)                                                  # whole head visible, room to breathe
    head = head.resize((hw, int(head.height * hw / head.width)), Image.LANCZOS)
    sh = Image.new("RGBA", head.size, (0, 0, 0, 0))
    sh.paste(NAVY_DEEP + (120,), (0, 0), head.getchannel("A"))
    y = int(s * .17)                                                  # body runs off the bottom edge
    bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(s // 70)), ((s - head.width) // 2, y + s // 60))
    bg.alpha_composite(head, ((s - head.width) // 2, y))
    for x, yy, z in ((.16, .2, .085), (.84, .26, .06), (.8, .12, .035)):
        st = _star(int(s * z), WHITE)
        bg.alpha_composite(st, (int(s * x - st.width / 2), int(s * yy - st.height / 2)))
    ring = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([s * .012, s * .012, s * .988, s * .988], outline=WHITE + (255,),
                                 width=int(s * .022))
    bg.alpha_composite(ring)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bg.resize((size, size), Image.LANCZOS).convert("RGB").save(out, "PNG", optimize=True)
    return out


def watermark(avatar_png: Path, out: Path, size: int = 150) -> Path:
    """YouTube video watermark: the avatar as a circle with a white border, transparent outside."""
    a = Image.open(avatar_png).convert("RGBA").resize((size * 4, size * 4), Image.LANCZOS)
    res = Image.new("RGBA", a.size, (0, 0, 0, 0))
    ImageDraw.Draw(res).ellipse([0, 0, a.width - 1, a.height - 1], fill=WHITE + (255,))
    inner = Image.new("L", a.size, 0)
    ImageDraw.Draw(inner).ellipse([22, 22, a.width - 23, a.height - 23], fill=255)
    res.paste(a, (0, 0), inner)
    res.resize((size, size), Image.LANCZOS).save(out, "PNG", optimize=True)
    return Path(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    d = Path(ap.parse_args().out_dir)
    d.mkdir(parents=True, exist_ok=True)
    print(banner(d / "banner-2560x1440.png"))
    av = avatar(d / "profile-800x800.png")
    print(av)
    print(watermark(av, d / "watermark-150x150.png"))
    logo(1600).save(d / "logo.png", "PNG", optimize=True)
    print(d / "logo.png")


if __name__ == "__main__":
    main()
