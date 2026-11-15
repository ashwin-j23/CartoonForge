"""The channel intro ("entry animation"): ~8 s, 1920x1080 @ 24 fps, theme jingle + gentle sound effects.

Storyboard
  0.0-0.7  a soft iris opens on the sunny meadow
  0.3-1.4  Sunny rises over the hills (whoosh)
  1.1-2.6  Hoppy, the star, hops in from the right in three bouncy hops (boing x3), lands centre
  2.5-3.8  the friends pop up one by one: Pip, Mimi, Bo, Zuzu, Nana Owl (pop x5)
  3.6-5.0  the channel name drops in letter by letter and bounces, in the palette's colours (pops)
  4.9-5.7  the tagline slides up in a pill; sparkles drift
  5.6-7.3  everyone waves, Hoppy does a happy hop, a chime; characters bob and blink
  7.3-8.0  a soft plum iris closes

Kid-safe: no flashes (luminance changes are slow), no scary motion, bright but age-capped colour.
`python -m app.render.intro OUT.mp4 [--name "Hoppy Hop Hop"]` renders it; `layers()` exports the pieces for SVGator.
"""
from __future__ import annotations

import base64
import io
import math
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import config
from . import music, palette, sets
from .characters import shadow, sprite
from .common import OUT, ease_in_out, ease_out, ease_out_back, rounded, text_img

W, H, FPS, DUR = 1920, 1080, 24, 8.0
FRIENDS = [("pip", .1, 2.55), ("mimi", .23, 2.75), ("bo", .68, 2.95), ("zuzu", .8, 3.15), ("nana", .915, 3.35)]
TAGLINE = "Songs, stories & smiles!"
SONG_AT = .48                     # the jingle starts here: its beats are at .6, 1.1, 1.6 ("Hop-py! Hop! Hop!")
SONG_HOPS = (3.1, 3.6)            # ...and the second "Hop! Hop!" (2.6 = "Hop-py")
PALETTE = "rainbow_playground"


def _blink(t, seed):
    return (t + seed * .53) % (2.9 + seed * .31) < .12


def _hop(t, t0, t1, hops):
    """Position 0..1 along the path and the hop height 0..1 for a sequence of hops between t0 and t1."""
    k = max(0.0, min(1.0, (t - t0) / (t1 - t0)))
    ph = (k * hops) % 1 if k < 1 else 1.0
    return ease_in_out(k), (math.sin(ph * math.pi) if k < 1 else 0.0), ph


def _iris(f: Image.Image, k: float) -> Image.Image:
    if k <= .01:
        return f
    r = math.hypot(W, H) / 2 * (1 - k)
    m = Image.new("L", (W, H), 255)
    ImageDraw.Draw(m).ellipse([W / 2 - r, H * .55 - r, W / 2 + r, H * .55 + r], fill=0)
    f.paste((70, 50, 110), (0, 0), m.filter(ImageFilter.GaussianBlur(6)))
    return f


def _sparkle(size, col):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size / 2
    pts = []
    for i in range(8):
        a = i * math.pi / 4
        r = c if i % 2 == 0 else c * .32
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    d.polygon(pts, fill=col + (235,))
    return im


def _letters(name: str, size: int):
    from .branding import brand_letters                    # same logo letters as the banner
    return list(brand_letters(name, int(size * .9)))


def frame(t: float, name: str, bg: Image.Image, letters, tag_img) -> Image.Image:
    f = bg.copy()
    sets.overlay(f, "meadow", t, avoid=(.06, .34))         # keep clouds clear of the channel name
    ground = H * .94

    # Sunny rises
    k = ease_out((t - .3) / 1.1)
    if k > 0:
        s = int(H * .2)
        sp = sprite("sunny", s, 1 if 1.2 < t < 1.6 else 0, "closed" if _blink(t, 1) else "open", "happy", "down")
        sp = sp.rotate(math.sin(t * .9) * 5, resample=Image.BILINEAR)
        x, y = W * .915, H * (.62 - .49 * k) + math.sin(t * 1.3) * H * .006
        f.paste(sp, (int(x - sp.width / 2), int(y - sp.height / 2)), sp)

    # friends pop up (behind Hoppy)
    for i, (cid, xf, t0) in enumerate(FRIENDS):
        k = ease_out_back((t - t0) / .45)
        if k <= .02:
            continue
        wave_on = t > 5.6 + i * .12
        arms = ("wave" if int((t - 5.6) * 2.2 + i) % 2 else "up") if wave_on else "down"
        emo = "excited" if wave_on else "happy"
        h = int(H * .3 * {"pip": .82, "mimi": .95, "bo": 1.12, "zuzu": .95, "nana": .95}[cid])
        sp = sprite(cid, h, 1 if wave_on and int(t * 5 + i) % 3 == 0 else 0,
                    "closed" if _blink(t, i + 2) else "open", emo, arms)
        bob = math.sin(t * 3 + i) * H * .005
        w2, h2 = max(1, int(sp.width * k)), max(1, int(sp.height * k))
        img = sp if k > .99 and abs(k - 1) < .01 else sp.resize((w2, h2), Image.BILINEAR)
        x = W * xf
        sh = shadow(int(sp.width * .7))
        f.paste(sh, (int(x - sh.width / 2), int(ground - sh.height / 2)), sh)
        f.paste(img, (int(x - img.width / 2), int(ground - img.height + bob)), img)

    # Hoppy hops in on the song: lands on "Hop!" (1.1 s) and "Hop!" (1.6 s), reaches the middle at 2.1 s,
    # then two little hops in place on the second "Hop! Hop!" (3.1 s, 3.6 s), and a happy hop at the end
    pos, hop, ph = _hop(t, .6, 2.1, 3)
    if t >= .6:
        x = W * (1.15 - .65 * pos)
        lift = hop * H * .16
        for land in SONG_HOPS:
            if land - .25 <= t <= land:
                lift = math.sin((t - land + .25) / .25 * math.pi) * H * .07
        if 6.3 <= t <= 6.9:                                     # the happy hop
            q = (t - 6.3) / .6
            lift = math.sin(q * math.pi) * H * .12
        squash = ((ph < .1 or ph > .9) and t < 2.1) or any(0 <= t - land < .08 for land in SONG_HOPS)
        emo = "excited" if t > 4.8 or hop > .2 else "happy"
        arms = "up" if hop > .3 or 6.3 <= t <= 6.9 else ("wave" if t > 5.4 and int(t * 2.4) % 2 else "down")
        sp = sprite("hoppy", int(H * .4), 2 if 6.3 <= t <= 6.9 or 4.9 < t < 5.3 else 0,
                    "closed" if _blink(t, 7) else "open", emo, arms)
        if squash:
            sp = sp.resize((int(sp.width * 1.1), int(sp.height * .9)), Image.BILINEAR)
        elif hop > .25:
            sp = sp.resize((int(sp.width * .95), int(sp.height * 1.06)), Image.BILINEAR)
        sh = shadow(int(sp.width * .75 * (1 - min(.45, lift / H * 2))))
        f.paste(sh, (int(x - sh.width / 2), int(ground - sh.height / 2)), sh)
        f.paste(sp, (int(x - sp.width / 2), int(ground - sp.height - lift + H * .01)), sp)

    # channel name, letter by letter
    total = sum((im.width if im else letters[0].width * .35) for im in letters)
    x = W / 2 - total / 2
    y = H * .2
    for i, im in enumerate(letters):
        if im is None:
            x += letters[0].width * .35
            continue
        t0 = 3.6 + i * .085
        k = (t - t0) / .55
        if k > 0:
            drop = (1 - ease_out_back(min(1, k))) * -H * .25
            bob = math.sin(t * 3.4 + i * .6) * H * .007 if k >= 1 else 0
            f.paste(im, (int(x), int(y - im.height / 2 + drop + bob)), im)
        x += im.width

    # tagline pill
    k = ease_out_back((t - 4.9) / .5)
    if k > .02:
        f.paste(tag_img, (int(W / 2 - tag_img.width / 2), int(H * .36 + (1 - k) * H * .06)), tag_img)

    # sparkles drift around the name (soft, no flashing)
    for j in range(7):
        t0 = 4.0 + j * .35
        if t < t0:
            continue
        a = (t - t0) / 2.4
        if a > 1:
            continue
        al = math.sin(a * math.pi)
        sp = _sparkle(int(H * (.03 + .015 * (j % 3))), palette.accent(j + 1))
        sp.putalpha(sp.getchannel("A").point(lambda v, al=al: int(v * al)))
        sx = W * (.2 + .6 * ((j * .37) % 1))
        sy = H * (.1 + .25 * ((j * .61) % 1)) - a * H * .05
        f.paste(sp, (int(sx), int(sy)), sp)

    if t < .7:
        f = _iris(f, 1 - ease_out(t / .7))
    elif t > DUR - .7:
        f = _iris(f, ease_in_out((t - (DUR - .7)) / .7))
    return f


def soundtrack(name: str, out: Path) -> Path:
    n = int(DUR * music.SR)
    L, R = np.zeros(n, np.float32), np.zeros(n, np.float32)

    def add(x, t, gain=1.0, pan=0.0):
        x = np.asarray(x, np.float32)
        if x.ndim == 2:
            l, r = x[:, 0], x[:, 1]
        else:
            l, r = x * (1 - max(0, pan)), x * (1 + min(0, pan))
        i = int(t * music.SR)
        m = max(0, min(len(l), n - i))
        L[i:i + m] += l[:m] * gain
        R[i:i + m] += r[:m] * gain

    th = music.theme(name)
    if th.ndim == 1:
        th = np.stack([th, th], 1)
    add(th, SONG_AT, .95)
    add(music.sfx("whoosh"), .1, .6)
    for i, (_, _, t0) in enumerate(FRIENDS):
        add(music.sfx("pop", i), t0 + .05, .8, -.6 + i * .3)
    for i in range(0, len(name), 2):
        add(music.sfx("pop", 10 + i), 3.6 + i * .085 + .35, .35)
    add(music.sfx("chime"), 6.0, .7)
    fade = np.ones(n, np.float32)
    k = int(.6 * music.SR)
    fade[-k:] = np.linspace(1, 0, k)
    mix = np.stack([L * fade, R * fade], 1)
    mix /= max(1e-6, float(np.max(np.abs(mix)))) / .89
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(music.SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return out


def _tagline(text: str):
    ti = text_img(text, int(H * .055), fill=(255, 255, 255), stroke=OUT, stroke_w=.1)
    pill = rounded(ti.width + int(H * .12), int(H * .1), int(H * .05), palette.button(), outline=(255, 255, 255), width=5)
    pill.alpha_composite(ti, ((pill.width - ti.width) // 2, (pill.height - ti.height) // 2))
    return pill


def render(out: Path, name: str = "Hoppy Hop Hop", tagline: str = TAGLINE, log=print) -> Path:
    from .styles import set_style
    set_style("classic")
    palette.set_current(PALETTE, "preschool")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bg = sets.background("meadow", W, H, palette.vivid_cap("preschool")).copy()
    letters = _letters(name, int(H * .12))
    tag = _tagline(tagline)
    wav = soundtrack(name, out.with_suffix(".wav"))
    cmd = [config.FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", "17",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(DUR * FPS)):
        p.stdin.write(frame(i / FPS, name, bg, letters, tag).convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    wav.unlink(missing_ok=True)
    log(f"Intro rendered: {out}")
    return out


# ---------------------------------------------------------------- SVGator layers
def _b64(im: Image.Image, fmt="PNG") -> str:
    buf = io.BytesIO()
    im.save(buf, fmt, **({"quality": 88} if fmt == "JPEG" else {"optimize": True}))
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()


def layers(out: Path, name: str = "Hoppy Hop Hop", tagline: str = TAGLINE, scale: float = .5) -> Path:
    """A layered SVG of the intro's final frame for SVGator: background, Sunny, each friend, Hoppy, each letter
    of the name, the tagline, sparkles — every piece its own named group, positioned where the video ends, so
    each can be keyframed in SVGator. Raster pieces are embedded PNGs; the canvas is 1920x1080 scaled by `scale`."""
    from .styles import set_style
    set_style("classic")
    palette.set_current(PALETTE, "preschool")
    sw, sh_ = int(W * scale), int(H * scale)
    s = scale
    parts = []

    def img(id_, im, x, y):
        w, h = int(im.width * s), int(im.height * s)
        im2 = im.resize((max(1, w), max(1, h)), Image.LANCZOS)
        parts.append(f'<g id="{id_}"><image href="{_b64(im2)}" x="{x * s:.1f}" y="{y * s:.1f}" '
                     f'width="{w}" height="{h}"/></g>')

    bg = sets.background("meadow", W, H, palette.vivid_cap("preschool")).copy()
    sets.overlay(bg, "meadow", 0)
    bgs = bg.resize((sw, sh_), Image.LANCZOS)
    parts.append(f'<g id="background"><image href="{_b64(bgs.convert("RGB"), "JPEG")}" x="0" y="0" width="{sw}" height="{sh_}"/></g>')
    ground = H * .94
    sun = sprite("sunny", int(H * .2), 0, "open", "happy", "down")
    img("sunny", sun, W * .915 - sun.width / 2, H * .13 - sun.height / 2)
    for cid, xf, _ in FRIENDS:
        h = int(H * .3 * {"pip": .82, "mimi": .95, "bo": 1.12, "zuzu": .95, "nana": .95}[cid])
        sp = sprite(cid, h, 0, "open", "excited", "wave")
        img(cid, sp, W * xf - sp.width / 2, ground - sp.height)
    hp = sprite("hoppy", int(H * .4), 2, "open", "excited", "wave")
    img("hoppy", hp, W * .5 - hp.width / 2, ground - hp.height + H * .01)
    letters = _letters(name, int(H * .12))
    total = sum((im.width if im else letters[0].width * .35) for im in letters)
    x = W / 2 - total / 2
    for i, im in enumerate(letters):
        if im is None:
            x += letters[0].width * .35
            continue
        img(f"letter_{i:02d}_{name[i]}", im, x, H * .2 - im.height / 2)
        x += im.width
    tag = _tagline(tagline)
    img("tagline", tag, W / 2 - tag.width / 2, H * .36)
    for j in range(5):
        sp = _sparkle(int(H * (.03 + .015 * (j % 3))), palette.accent(j + 1))
        img(f"sparkle_{j}", sp, W * (.2 + .6 * ((j * .37) % 1)), H * (.1 + .25 * ((j * .61) % 1)))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="{sw}" height="{sh_}" viewBox="0 0 {sw} {sh_}">' + "".join(parts) + "</svg>")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg)
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--name", default="Hoppy Hop Hop")
    ap.add_argument("--tagline", default=TAGLINE)
    ap.add_argument("--svg", default="")
    a = ap.parse_args()
    render(Path(a.out), a.name, a.tagline)
    if a.svg:
        print("layers:", layers(Path(a.svg), a.name, a.tagline))
