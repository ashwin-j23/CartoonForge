"""Icon library: friendly objects drawn in code (no stock art, no licences, same style forever).

icon(name, size) -> RGBA sprite. Every icon has a soft outline and a highlight, like a picture book.
Unknown names fall back to a star, and the card shows the word under it, so the child still hears + sees it.
"""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image

from .common import OUT, SS, canvas, ell, finish, lighten, darken


def _poly(d, pts, fill, w):
    d.polygon(pts, fill=fill, outline=OUT)
    d.line(pts + [pts[0]], fill=OUT, width=int(w), joint="curve")


def _star_pts(cx, cy, r1, r2, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r1 if i % 2 == 0 else r2
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _heart_pts(cx, cy, s):
    pts = []
    for i in range(80):
        t = math.pi * 2 * i / 80
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * s / 34, cy + y * s / 34))
    return pts


def _shine(d, cx, cy, r):
    ell(d, cx, cy, r, r * 0.6, (255, 255, 255))


def _eyes(d, cx, cy, gap, r):
    for sx in (-1, 1):
        ell(d, cx + sx * gap, cy, r, r, OUT)
        ell(d, cx + sx * gap + r * 0.3, cy - r * 0.35, r * 0.35, r * 0.35, (255, 255, 255))


# each fn draws into a square canvas of side S (already supersampled); w = outline width
def apple(d, S, w):
    c = S / 2
    ell(d, c, c + S * .06, S * .36, S * .33, (235, 60, 60), OUT, w)
    d.line([(c, c - S * .22), (c + S * .04, c - S * .38)], fill=(110, 70, 40), width=int(w * 1.6))
    ell(d, c + S * .14, c - S * .3, S * .1, S * .05, (90, 190, 90), OUT, w * .6)
    _shine(d, c - S * .15, c - S * .06, S * .07)


def banana(d, S, w):
    c = S / 2
    outer = [(c + math.cos(math.radians(a)) * S * .42, c - S * .12 + math.sin(math.radians(a)) * S * .42) for a in range(15, 166, 10)]
    inner = [(c + math.cos(math.radians(a)) * S * .3, c - S * .22 + math.sin(math.radians(a)) * S * .3) for a in range(160, 19, -10)]
    _poly(d, outer + inner, (255, 220, 70), w)
    d.line([outer[0], (outer[0][0] + S * .05, outer[0][1] - S * .06)], fill=(120, 90, 50), width=int(w * 1.5))


def orange(d, S, w):
    c = S / 2
    ell(d, c, c + S * .04, S * .36, S * .36, (255, 150, 40), OUT, w)
    ell(d, c + S * .06, c - S * .3, S * .1, S * .05, (90, 190, 90), OUT, w * .6)
    _shine(d, c - S * .14, c - S * .1, S * .07)


def strawberry(d, S, w):
    c = S / 2
    _poly(d, [(c - S * .33, c - S * .16), (c + S * .33, c - S * .16), (c + S * .2, c + S * .22), (c, c + S * .38),
              (c - S * .2, c + S * .22)], (240, 60, 80), w)
    ell(d, c, c - S * .2, S * .3, S * .1, (240, 60, 80))
    for dx, dy in [(-.15, 0), (.05, -.05), (.15, .08), (-.05, .15), (-.18, .12), (.02, .27)]:
        ell(d, c + dx * S, c + dy * S, S * .022, S * .03, (255, 235, 120))
    _poly(d, [(c - S * .2, c - S * .25), (c, c - S * .17), (c + S * .2, c - S * .25), (c, c - S * .33)], (80, 180, 80), w * .6)


def cherry(d, S, w):
    c = S / 2
    d.line([(c - S * .15, c + S * .1), (c + S * .05, c - S * .35), (c + S * .17, c + S * .1)], fill=(90, 140, 60), width=int(w * 1.4))
    for dx in (-.15, .17):
        ell(d, c + dx * S, c + S * .18, S * .16, S * .16, (220, 30, 60), OUT, w)
        _shine(d, c + dx * S - S * .05, c + S * .12, S * .04)


def carrot(d, S, w):
    c = S / 2
    _poly(d, [(c - S * .14, c - S * .2), (c + S * .14, c - S * .2), (c, c + S * .42)], (255, 140, 30), w)
    for a in (-25, 0, 25):
        x = c + math.sin(math.radians(a)) * S * .15
        d.line([(c, c - S * .2), (x, c - S * .42)], fill=(80, 170, 70), width=int(S * .06))


def star(d, S, w, color=(255, 210, 50)):
    c = S / 2
    _poly(d, _star_pts(c, c + S * .03, S * .44, S * .2), color, w)
    _eyes(d, c, c + S * .02, S * .09, S * .035)
    d.arc([c - S * .07, c + S * .03, c + S * .07, c + S * .13], 20, 160, fill=OUT, width=int(w * .8))


def heart(d, S, w, color=(245, 80, 120)):
    c = S / 2
    _poly(d, _heart_pts(c, c + S * .02, S * .9), color, w)
    _shine(d, c - S * .17, c - S * .14, S * .06)


def ball(d, S, w):
    c = S / 2
    ell(d, c, c, S * .4, S * .4, (255, 90, 90), OUT, w)
    d.chord([c - S * .4, c - S * .4, c + S * .4, c + S * .4], 200, 340, fill=(255, 220, 70))
    d.chord([c - S * .4, c - S * .4, c + S * .4, c + S * .4], 20, 160, fill=(80, 150, 240))
    ell(d, c, c, S * .4, S * .4, None, OUT, w)
    _shine(d, c - S * .16, c - S * .2, S * .07)


def balloon(d, S, w, color=(240, 80, 110)):
    c = S / 2
    d.line([(c, c + S * .26), (c - S * .04, c + S * .48)], fill=OUT, width=int(w * .7))
    ell(d, c, c - S * .06, S * .3, S * .34, color, OUT, w)
    _poly(d, [(c - S * .05, c + S * .3), (c + S * .05, c + S * .3), (c, c + S * .26)], color, w * .5)
    _shine(d, c - S * .12, c - S * .2, S * .06)


def flower(d, S, w):
    c = S / 2
    d.line([(c, c + S * .1), (c, c + S * .48)], fill=(80, 170, 70), width=int(S * .05))
    for i in range(6):
        a = math.radians(i * 60)
        ell(d, c + math.cos(a) * S * .2, c - S * .1 + math.sin(a) * S * .2, S * .14, S * .14, (255, 130, 180), OUT, w)
    ell(d, c, c - S * .1, S * .14, S * .14, (255, 210, 60), OUT, w)


def tree(d, S, w):
    c = S / 2
    d.rectangle([c - S * .07, c + S * .05, c + S * .07, c + S * .45], fill=(150, 100, 60), outline=OUT, width=int(w))
    for dx, dy, r in [(-.15, -.05, .2), (.15, -.05, .2), (0, -.22, .24)]:
        ell(d, c + dx * S, c + dy * S, S * r, S * r, (90, 190, 90), OUT, w)
    ell(d, c, c - .05 * S, S * .2, S * .14, (90, 190, 90))


def leaf(d, S, w):
    c = S / 2
    d.ellipse([c - S * .2, c - S * .38, c + S * .2, c + S * .38], fill=(100, 190, 80), outline=OUT, width=int(w))
    d.line([(c, c - S * .32), (c, c + S * .46)], fill=darken((100, 190, 80)), width=int(w))


def sun(d, S, w):
    c = S / 2
    for i in range(12):
        a = math.radians(i * 30)
        d.line([(c + math.cos(a) * S * .3, c + math.sin(a) * S * .3), (c + math.cos(a) * S * .46, c + math.sin(a) * S * .46)],
               fill=(255, 170, 40), width=int(S * .05))
    ell(d, c, c, S * .28, S * .28, (255, 210, 60), OUT, w)
    _eyes(d, c, c - S * .03, S * .09, S * .035)
    d.arc([c - S * .1, c, c + S * .1, c + S * .12], 20, 160, fill=OUT, width=int(w * .8))


def moon(d, S, w):
    c = S / 2
    ell(d, c, c, S * .38, S * .38, (255, 230, 140), OUT, w)
    ell(d, c + S * .18, c - S * .1, S * .32, S * .32, (0, 0, 0, 0))
    _eyes(d, c - S * .14, c + S * .02, S * .0, S * .03)


def cloud(d, S, w):
    c = S / 2
    for dx, dy, r in [(-.2, .05, .16), (0, -.06, .22), (.2, .05, .16)]:
        ell(d, c + dx * S, c + dy * S, S * r, S * r, (255, 255, 255), OUT, w)
    d.rectangle([c - S * .2, c + S * .02, c + S * .2, c + S * .2], fill=(255, 255, 255))
    d.line([(c - S * .2, c + S * .21), (c + S * .2, c + S * .21)], fill=OUT, width=int(w))
    for dx, dy, r in [(-.2, .05, .16 - .02), (0, -.06, .22 - .02), (.2, .05, .16 - .02)]:
        ell(d, c + dx * S, c + dy * S, S * r, S * r, (255, 255, 255))


def raindrop(d, S, w):
    c = S / 2
    _poly(d, [(c, c - S * .4)] + [(c + math.cos(math.radians(a)) * S * .24, c + S * .12 + math.sin(math.radians(a)) * S * .24)
                                  for a in range(-20, 210, 10)], (90, 170, 245), w)


def snowflake(d, S, w):
    c = S / 2
    for i in range(6):
        a = math.radians(i * 60)
        x, y = c + math.cos(a) * S * .4, c + math.sin(a) * S * .4
        d.line([(c, c), (x, y)], fill=(120, 190, 255), width=int(S * .05))
        for s2 in (-1, 1):
            a2 = a + s2 * 0.6
            mx, my = c + math.cos(a) * S * .25, c + math.sin(a) * S * .25
            d.line([(mx, my), (mx + math.cos(a2) * S * .1, my + math.sin(a2) * S * .1)], fill=(120, 190, 255), width=int(S * .04))


def rainbow(d, S, w):
    c = S / 2
    cols = [(240, 70, 70), (255, 150, 50), (255, 215, 60), (90, 195, 95), (70, 140, 235), (155, 105, 215)]
    for i, col in enumerate(cols):
        r = S * (.46 - i * .055)
        d.pieslice([c - r, c - r + S * .2, c + r, c + r + S * .2], 180, 360, fill=col)
    r = S * (.46 - 6 * .055)
    d.pieslice([c - r, c - r + S * .2, c + r, c + r + S * .2], 180, 360, fill=(0, 0, 0, 0))


def fish(d, S, w, color=(255, 150, 60)):
    c = S / 2
    _poly(d, [(c + S * .2, c), (c + S * .45, c - S * .2), (c + S * .45, c + S * .2)], color, w)
    ell(d, c - S * .05, c, S * .3, S * .2, color, OUT, w)
    _eyes(d, c - S * .2, c - S * .04, 0, S * .04)


def duck(d, S, w):
    c = S / 2
    ell(d, c + S * .05, c + S * .14, S * .34, S * .22, (255, 215, 60), OUT, w)
    ell(d, c - S * .18, c - S * .14, S * .16, S * .16, (255, 215, 60), OUT, w)
    _poly(d, [(c - S * .32, c - S * .14), (c - S * .46, c - S * .08), (c - S * .32, c - S * .04)], (255, 140, 40), w * .7)
    _eyes(d, c - S * .22, c - S * .18, 0, S * .03)
    d.arc([c - S * .05, c + S * .02, c + S * .3, c + S * .25], 200, 330, fill=OUT, width=int(w * .8))


def bird(d, S, w, color=(90, 170, 240)):
    c = S / 2
    ell(d, c, c, S * .3, S * .26, color, OUT, w)
    _poly(d, [(c - S * .28, c - S * .04), (c - S * .42, c + S * .02), (c - S * .28, c + S * .06)], (255, 170, 40), w * .7)
    _eyes(d, c - S * .14, c - S * .08, 0, S * .035)
    d.chord([c - S * .05, c - S * .05, c + S * .28, c + S * .2], 0, 180, fill=darken(color, .15), outline=OUT, width=int(w * .7))


def butterfly(d, S, w):
    c = S / 2
    for sx in (-1, 1):
        ell(d, c + sx * S * .2, c - S * .12, S * .2, S * .18, (180, 120, 230), OUT, w)
        ell(d, c + sx * S * .16, c + S * .16, S * .14, S * .13, (255, 150, 200), OUT, w)
        ell(d, c + sx * S * .2, c - S * .12, S * .06, S * .06, (255, 230, 120))
    ell(d, c, c, S * .05, S * .26, (70, 60, 90), OUT, w * .5)
    for sx in (-1, 1):
        d.line([(c, c - S * .24), (c + sx * S * .1, c - S * .4)], fill=OUT, width=int(w * .7))


def bee(d, S, w):
    c = S / 2
    for sx in (-1, 1):
        ell(d, c + sx * S * .1, c - S * .25, S * .14, S * .12, (220, 240, 255), OUT, w * .7)
    ell(d, c, c + S * .04, S * .34, S * .24, (255, 210, 50), OUT, w)
    for dx in (-.08, .1):
        d.rectangle([c + dx * S, c - S * .18, c + dx * S + S * .07, c + S * .26], fill=(60, 50, 60))
    ell(d, c, c + S * .04, S * .34, S * .24, None, OUT, w)
    _eyes(d, c - S * .2, c - S * .02, 0, S * .035)


def ladybug(d, S, w):
    c = S / 2
    ell(d, c, c + S * .05, S * .34, S * .3, (230, 50, 50), OUT, w)
    ell(d, c, c - S * .25, S * .16, S * .12, (60, 50, 60), OUT, w)
    d.line([(c, c - S * .18), (c, c + S * .34)], fill=OUT, width=int(w))
    for dx, dy in [(-.15, -.02), (.15, -.02), (-.12, .17), (.12, .17)]:
        ell(d, c + dx * S, c + dy * S, S * .055, S * .055, (60, 50, 60))


def snail(d, S, w):
    c = S / 2
    ell(d, c, c + S * .26, S * .42, S * .1, (170, 220, 140), OUT, w)
    ell(d, c + S * .05, c, S * .26, S * .26, (240, 170, 90), OUT, w)
    d.arc([c - S * .08, c - S * .13, c + S * .18, c + S * .13], 0, 300, fill=OUT, width=int(w))
    _eyes(d, c - S * .34, c + S * .08, 0, S * .03)


def frog(d, S, w):
    c = S / 2
    ell(d, c, c + S * .1, S * .38, S * .28, (110, 200, 90), OUT, w)
    for sx in (-1, 1):
        ell(d, c + sx * S * .18, c - S * .18, S * .12, S * .12, (110, 200, 90), OUT, w)
        ell(d, c + sx * S * .18, c - S * .18, S * .06, S * .06, OUT)
    d.arc([c - S * .2, c, c + S * .2, c + S * .22], 15, 165, fill=OUT, width=int(w))


def cat(d, S, w):
    c = S / 2
    for sx in (-1, 1):
        _poly(d, [(c + sx * S * .32, c - S * .1), (c + sx * S * .3, c - S * .42), (c + sx * S * .08, c - S * .26)], (250, 170, 90), w)
    ell(d, c, c, S * .34, S * .3, (250, 170, 90), OUT, w)
    _eyes(d, c, c - S * .03, S * .12, S * .04)
    ell(d, c, c + S * .08, S * .04, S * .03, (240, 110, 130))
    for sx in (-1, 1):
        d.line([(c + sx * S * .12, c + S * .1), (c + sx * S * .38, c + S * .06)], fill=OUT, width=int(w * .5))


def dog(d, S, w):
    c = S / 2
    ell(d, c, c, S * .32, S * .3, (210, 160, 110), OUT, w)
    for sx in (-1, 1):
        ell(d, c + sx * S * .3, c + S * .02, S * .1, S * .2, (150, 100, 70), OUT, w)
    _eyes(d, c, c - S * .05, S * .11, S * .04)
    ell(d, c, c + S * .1, S * .07, S * .05, OUT)


def pig(d, S, w):
    c = S / 2
    for sx in (-1, 1):
        _poly(d, [(c + sx * S * .3, c - S * .16), (c + sx * S * .32, c - S * .38), (c + sx * S * .12, c - S * .26)], (255, 170, 190), w)
    ell(d, c, c, S * .36, S * .3, (255, 180, 200), OUT, w)
    ell(d, c, c + S * .08, S * .12, S * .08, (255, 140, 170), OUT, w * .7)
    for sx in (-1, 1):
        ell(d, c + sx * S * .04, c + S * .08, S * .02, S * .03, OUT)
    _eyes(d, c, c - S * .1, S * .13, S * .035)


def cow(d, S, w):
    c = S / 2
    ell(d, c, c, S * .34, S * .32, (250, 250, 250), OUT, w)
    ell(d, c - S * .14, c - S * .12, S * .1, S * .08, (60, 50, 60))
    ell(d, c, c + S * .14, S * .2, S * .13, (255, 190, 200), OUT, w * .7)
    _eyes(d, c, c - S * .05, S * .13, S * .035)
    for sx in (-1, 1):
        ell(d, c + sx * S * .38, c - S * .12, S * .1, S * .05, (250, 250, 250), OUT, w * .7)


def elephant(d, S, w):
    c = S / 2
    g = (160, 170, 195)
    for sx in (-1, 1):
        ell(d, c + sx * S * .28, c - S * .02, S * .18, S * .22, lighten(g, .2), OUT, w)
    ell(d, c, c - S * .02, S * .27, S * .27, g, OUT, w)
    d.line([(c, c + S * .1), (c, c + S * .34), (c + S * .1, c + S * .42)], fill=OUT, width=int(S * .12 + w * 2), joint="curve")
    d.line([(c, c + S * .1), (c, c + S * .34), (c + S * .1, c + S * .42)], fill=g, width=int(S * .12), joint="curve")
    _eyes(d, c, c - S * .08, S * .1, S * .035)


def lion(d, S, w):
    c = S / 2
    for i in range(14):
        a = math.radians(i * 360 / 14)
        ell(d, c + math.cos(a) * S * .3, c + math.sin(a) * S * .3, S * .13, S * .13, (215, 120, 50), OUT, w * .6)
    ell(d, c, c, S * .3, S * .3, (255, 200, 90), OUT, w)
    _eyes(d, c, c - S * .06, S * .1, S * .035)
    ell(d, c, c + S * .07, S * .06, S * .04, OUT)
    d.arc([c - S * .1, c + S * .05, c + S * .1, c + S * .17], 20, 160, fill=OUT, width=int(w * .8))


def egg(d, S, w):
    c = S / 2
    ell(d, c, c + S * .05, S * .28, S * .36, (255, 245, 225), OUT, w)
    _shine(d, c - S * .1, c - S * .12, S * .05)


def car(d, S, w, color=(240, 80, 80)):
    c = S / 2
    d.rounded_rectangle([c - S * .42, c - S * .02, c + S * .42, c + S * .22], S * .08, fill=color, outline=OUT, width=int(w))
    d.rounded_rectangle([c - S * .24, c - S * .22, c + S * .2, c + S * .02], S * .08, fill=color, outline=OUT, width=int(w))
    d.rounded_rectangle([c - S * .18, c - S * .17, c + S * .14, c - S * .01], S * .04, fill=(200, 235, 255))
    for dx in (-.24, .24):
        ell(d, c + dx * S, c + S * .24, S * .1, S * .1, (60, 60, 70), OUT, w)
        ell(d, c + dx * S, c + S * .24, S * .04, S * .04, (200, 200, 210))


def bus(d, S, w):
    c = S / 2
    d.rounded_rectangle([c - S * .44, c - S * .26, c + S * .44, c + S * .22], S * .08, fill=(255, 200, 50), outline=OUT, width=int(w))
    for i in range(4):
        x = c - S * .36 + i * S * .19
        d.rounded_rectangle([x, c - S * .18, x + S * .14, c - S * .02], S * .03, fill=(200, 235, 255), outline=OUT, width=int(w * .5))
    for dx in (-.26, .26):
        ell(d, c + dx * S, c + S * .24, S * .09, S * .09, (60, 60, 70), OUT, w)


def boat(d, S, w):
    c = S / 2
    _poly(d, [(c - S * .42, c + S * .1), (c + S * .42, c + S * .1), (c + S * .28, c + S * .32), (c - S * .28, c + S * .32)], (240, 90, 80), w)
    d.line([(c, c + S * .1), (c, c - S * .4)], fill=OUT, width=int(w))
    _poly(d, [(c + S * .02, c - S * .38), (c + S * .3, c + S * .04), (c + S * .02, c + S * .04)], (255, 255, 255), w)


def rocket(d, S, w):
    c = S / 2
    _poly(d, [(c - S * .14, c + S * .2), (c - S * .3, c + S * .36), (c - S * .14, c + S * .02)], (240, 80, 80), w)
    _poly(d, [(c + S * .14, c + S * .2), (c + S * .3, c + S * .36), (c + S * .14, c + S * .02)], (240, 80, 80), w)
    d.ellipse([c - S * .15, c - S * .44, c + S * .15, c + S * .32], fill=(240, 240, 250), outline=OUT, width=int(w))
    ell(d, c, c - S * .08, S * .08, S * .08, (110, 190, 250), OUT, w * .7)
    _poly(d, [(c - S * .08, c + S * .32), (c + S * .08, c + S * .32), (c, c + S * .46)], (255, 180, 50), w * .5)


def plane(d, S, w):
    c = S / 2
    _poly(d, [(c - S * .05, c - S * .02), (c + S * .1, c - S * .4), (c + S * .2, c - S * .4), (c + S * .12, c - S * .02)], (90, 160, 240), w)
    d.rounded_rectangle([c - S * .44, c - S * .08, c + S * .44, c + S * .1], S * .09, fill=(245, 245, 250), outline=OUT, width=int(w))
    _poly(d, [(c - S * .05, c + S * .06), (c + S * .1, c + S * .36), (c + S * .2, c + S * .36), (c + S * .12, c + S * .06)], (90, 160, 240), w)
    for i in range(4):
        ell(d, c - S * .2 + i * S * .1, c, S * .025, S * .025, (110, 190, 250))


def train(d, S, w):
    c = S / 2
    d.rounded_rectangle([c - S * .42, c - S * .12, c + S * .1, c + S * .2], S * .04, fill=(80, 160, 240), outline=OUT, width=int(w))
    d.rounded_rectangle([c + S * .02, c - S * .32, c + S * .38, c + S * .2], S * .04, fill=(240, 80, 80), outline=OUT, width=int(w))
    d.rectangle([c - S * .32, c - S * .3, c - S * .2, c - S * .12], fill=(60, 60, 70), outline=OUT, width=int(w * .6))
    d.rounded_rectangle([c + S * .1, c - S * .24, c + S * .3, c - S * .06], S * .03, fill=(200, 235, 255))
    for dx in (-.3, -.08, .2):
        ell(d, c + dx * S, c + S * .24, S * .08, S * .08, (60, 60, 70), OUT, w)


def house(d, S, w):
    c = S / 2
    d.rectangle([c - S * .3, c - S * .06, c + S * .3, c + S * .38], fill=(255, 220, 160), outline=OUT, width=int(w))
    _poly(d, [(c - S * .4, c - S * .04), (c, c - S * .4), (c + S * .4, c - S * .04)], (220, 80, 70), w)
    d.rounded_rectangle([c - S * .08, c + S * .12, c + S * .08, c + S * .38], S * .03, fill=(150, 100, 60), outline=OUT, width=int(w * .7))
    d.rectangle([c + S * .13, c + S * .04, c + S * .25, c + S * .16], fill=(200, 235, 255), outline=OUT, width=int(w * .6))


def cake(d, S, w):
    c = S / 2
    d.rounded_rectangle([c - S * .34, c - S * .04, c + S * .34, c + S * .34], S * .05, fill=(255, 200, 220), outline=OUT, width=int(w))
    d.rounded_rectangle([c - S * .34, c - S * .1, c + S * .34, c + S * .06], S * .05, fill=(255, 250, 250), outline=OUT, width=int(w))
    for dx in (-.15, 0, .15):
        d.rectangle([c + dx * S - S * .02, c - S * .3, c + dx * S + S * .02, c - S * .1], fill=(120, 180, 250))
        ell(d, c + dx * S, c - S * .34, S * .03, S * .05, (255, 190, 50))


def cupcake(d, S, w):
    c = S / 2
    _poly(d, [(c - S * .28, c), (c + S * .28, c), (c + S * .2, c + S * .38), (c - S * .2, c + S * .38)], (120, 190, 250), w)
    for dx, dy, r in [(-.16, -.04, .14), (.16, -.04, .14), (0, -.16, .17)]:
        ell(d, c + dx * S, c + dy * S, S * r, S * r, (255, 190, 215), OUT, w)
    ell(d, c, c - S * .32, S * .06, S * .06, (230, 40, 60), OUT, w * .6)


def cup(d, S, w):
    c = S / 2
    d.arc([c + S * .12, c - S * .12, c + S * .42, c + S * .18], -90, 90, fill=OUT, width=int(S * .06))
    d.rounded_rectangle([c - S * .3, c - S * .24, c + S * .22, c + S * .32], S * .06, fill=(120, 200, 240), outline=OUT, width=int(w))


def book(d, S, w):
    c = S / 2
    d.rounded_rectangle([c - S * .38, c - S * .3, c + S * .38, c + S * .3], S * .04, fill=(90, 160, 240), outline=OUT, width=int(w))
    d.rectangle([c - S * .34, c - S * .26, c + S * .34, c + S * .22], fill=(255, 250, 240), outline=OUT, width=int(w * .6))
    d.line([(c, c - S * .26), (c, c + S * .22)], fill=OUT, width=int(w * .6))
    for i in range(3):
        y = c - S * .14 + i * S * .1
        d.line([(c - S * .26, y), (c - S * .06, y)], fill=(180, 180, 200), width=int(w * .5))
        d.line([(c + S * .06, y), (c + S * .26, y)], fill=(180, 180, 200), width=int(w * .5))


def toothbrush(d, S, w):
    c = S / 2
    d.rounded_rectangle([c - S * .42, c + S * .02, c + S * .2, c + S * .12], S * .05, fill=(90, 190, 240), outline=OUT, width=int(w))
    d.rounded_rectangle([c + S * .14, c - S * .02, c + S * .42, c + S * .1], S * .03, fill=(250, 250, 255), outline=OUT, width=int(w))
    for i in range(6):
        x = c + S * .17 + i * S * .042
        d.line([(x, c - S * .02), (x, c - S * .16)], fill=(255, 255, 255), width=int(S * .025))
        d.line([(x, c - S * .16), (x, c - S * .17)], fill=OUT, width=int(S * .015))


def sock(d, S, w):
    c = S / 2
    d.line([(c - S * .05, c - S * .38), (c - S * .05, c + S * .1), (c + S * .2, c + S * .3)], fill=OUT, width=int(S * .26 + w * 2), joint="curve")
    d.line([(c - S * .05, c - S * .38), (c - S * .05, c + S * .1), (c + S * .2, c + S * .3)], fill=(255, 120, 150), width=int(S * .26), joint="curve")
    d.line([(c - S * .18, c - S * .3), (c + S * .08, c - S * .3)], fill=(255, 255, 255), width=int(S * .05))


def drum(d, S, w):
    c = S / 2
    d.rectangle([c - S * .32, c - S * .12, c + S * .32, c + S * .26], fill=(240, 80, 80), outline=OUT, width=int(w))
    ell(d, c, c + S * .26, S * .32, S * .1, (240, 80, 80), OUT, w)
    d.rectangle([c - S * .32 + w, c + S * .1, c + S * .32 - w, c + S * .26], fill=(240, 80, 80))
    ell(d, c, c - S * .12, S * .32, S * .1, (250, 240, 220), OUT, w)
    for sx in (-1, 1):
        d.line([(c + sx * S * .1, c - S * .2), (c + sx * S * .36, c - S * .44)], fill=(160, 110, 60), width=int(S * .04))


def bell(d, S, w):
    c = S / 2
    _poly(d, [(c - S * .3, c + S * .22), (c - S * .2, c - S * .2), (c, c - S * .32), (c + S * .2, c - S * .2), (c + S * .3, c + S * .22)], (255, 200, 50), w)
    ell(d, c, c + S * .28, S * .07, S * .07, (230, 160, 40), OUT, w * .7)


def block(d, S, w):
    c = S / 2
    d.rounded_rectangle([c - S * .32, c - S * .32, c + S * .32, c + S * .32], S * .06, fill=(255, 180, 60), outline=OUT, width=int(w))
    d.rounded_rectangle([c - S * .22, c - S * .22, c + S * .22, c + S * .22], S * .04, fill=None, outline=lighten((255, 180, 60), .5), width=int(w))


def shell(d, S, w):
    c = S / 2
    d.pieslice([c - S * .38, c - S * .3, c + S * .38, c + S * .46], 180, 360, fill=(255, 190, 170), outline=OUT, width=int(w))
    for a in range(200, 360, 30):
        d.line([(c, c + S * .08), (c + math.cos(math.radians(a)) * S * .36, c + S * .08 + math.sin(math.radians(a)) * S * .36)],
               fill=darken((255, 190, 170), .15), width=int(w * .6))


def umbrella(d, S, w):
    c = S / 2
    d.pieslice([c - S * .42, c - S * .38, c + S * .42, c + S * .3], 180, 360, fill=(120, 110, 230), outline=OUT, width=int(w))
    d.line([(c, c - S * .04), (c, c + S * .34)], fill=OUT, width=int(w * 1.2))
    d.arc([c, c + S * .26, c + S * .14, c + S * .4], 0, 180, fill=OUT, width=int(w * 1.2))


def kite(d, S, w):
    c = S / 2
    _poly(d, [(c, c - S * .42), (c + S * .26, c - S * .08), (c, c + S * .24), (c - S * .26, c - S * .08)], (255, 120, 80), w)
    d.line([(c, c - S * .42), (c, c + S * .24)], fill=OUT, width=int(w * .5))
    d.line([(c, c + S * .24), (c - S * .1, c + S * .46)], fill=OUT, width=int(w * .5))


def planet(d, S, w):
    c = S / 2
    d.arc([c - S * .46, c - S * .1, c + S * .46, c + S * .2], 160, 380, fill=(255, 210, 120), width=int(S * .05))
    ell(d, c, c, S * .28, S * .28, (240, 160, 90), OUT, w)
    d.arc([c - S * .46, c - S * .1, c + S * .46, c + S * .2], 0, 160, fill=(255, 210, 120), width=int(S * .05))


def dinosaur(d, S, w):
    c = S / 2
    g = (110, 200, 110)
    _poly(d, [(c + S * .2, c + S * .1), (c + S * .46, c + S * .2), (c + S * .2, c + S * .24)], g, w)
    ell(d, c + S * .04, c + S * .12, S * .26, S * .2, g, OUT, w)
    d.line([(c - S * .12, c + S * .04), (c - S * .2, c - S * .26)], fill=OUT, width=int(S * .14 + w * 2))
    d.line([(c - S * .12, c + S * .04), (c - S * .2, c - S * .26)], fill=g, width=int(S * .14))
    ell(d, c - S * .24, c - S * .3, S * .13, S * .1, g, OUT, w)
    _eyes(d, c - S * .26, c - S * .33, 0, S * .03)
    for dx in (-.08, .14):
        d.rectangle([c + dx * S, c + S * .26, c + dx * S + S * .08, c + S * .4], fill=g, outline=OUT, width=int(w * .7))


def lamp(d, S, w):
    """Diya / oil lamp (festivals of light)."""
    c = S / 2
    d.chord([c - S * .36, c - S * .1, c + S * .36, c + S * .36], 0, 180, fill=(220, 120, 60), outline=OUT, width=int(w))
    _poly(d, [(c, c - S * .42), (c + S * .08, c - S * .14), (c, c - S * .06), (c - S * .08, c - S * .14)], (255, 200, 50), w * .6)


def lantern(d, S, w):
    c = S / 2
    d.line([(c, c - S * .46), (c, c - S * .3)], fill=OUT, width=int(w))
    ell(d, c, c, S * .3, S * .28, (235, 60, 60), OUT, w)
    for dx in (-.15, 0, .15):
        d.arc([c - S * .3 + (dx + .15) * S * 0, c - S * .28, c + S * .3, c + S * .28], 0, 0, fill=OUT)
        d.line([(c + dx * S, c - S * .27), (c + dx * S, c + S * .27)], fill=darken((235, 60, 60), .2), width=int(w * .6))
    d.rectangle([c - S * .12, c + S * .26, c + S * .12, c + S * .34], fill=(255, 200, 50), outline=OUT, width=int(w * .6))


def present(d, S, w):
    c = S / 2
    d.rectangle([c - S * .32, c - S * .12, c + S * .32, c + S * .36], fill=(90, 180, 240), outline=OUT, width=int(w))
    d.rectangle([c - S * .06, c - S * .12, c + S * .06, c + S * .36], fill=(255, 210, 60))
    for sx in (-1, 1):
        ell(d, c + sx * S * .12, c - S * .2, S * .12, S * .08, (255, 210, 60), OUT, w * .7)


def water(d, S, w):
    raindrop(d, S, w)


def hand(d, S, w):
    c = S / 2
    skin = (255, 205, 160)
    ell(d, c, c + S * .1, S * .24, S * .24, skin, OUT, w)
    for i, dx in enumerate((-.18, -.06, .06, .18)):
        d.rounded_rectangle([c + dx * S - S * .05, c - S * .38 + (abs(dx) * S * .3), c + dx * S + S * .05, c + S * .02], S * .05,
                            fill=skin, outline=OUT, width=int(w * .7))
    d.rounded_rectangle([c - S * .4, c - S * .04, c - S * .18, c + S * .06], S * .05, fill=skin, outline=OUT, width=int(w * .7))
    ell(d, c, c + S * .1, S * .22, S * .22, skin)


ICONS = {f.__name__: f for f in [
    apple, banana, orange, strawberry, cherry, carrot, star, heart, ball, balloon, flower, tree, leaf, sun, moon, cloud,
    raindrop, snowflake, rainbow, fish, duck, bird, butterfly, bee, ladybug, snail, frog, cat, dog, pig, cow, elephant,
    lion, egg, car, bus, boat, rocket, plane, train, house, cake, cupcake, cup, book, toothbrush, sock, drum, bell, block,
    shell, umbrella, kite, planet, dinosaur, lamp, lantern, present, water, hand]}
ALIASES = {"apples": "apple", "stars": "star", "ducks": "duck", "balls": "ball", "fishes": "fish", "flowers": "flower",
           "trees": "tree", "birds": "bird", "cars": "car", "boats": "boat", "bees": "bee", "eggs": "egg",
           "teeth": "toothbrush", "tooth": "toothbrush", "diya": "lamp", "candle": "lamp", "gift": "present",
           "kitten": "cat", "puppy": "dog", "chick": "duck", "dino": "dinosaur", "moon": "moon", "earth": "planet",
           "sheep": "cloud", "snow": "snowflake", "rain": "raindrop", "drop": "raindrop", "ship": "boat",
           "airplane": "plane", "aeroplane": "plane", "truck": "bus", "rock": "egg", "seed": "egg", "mango": "orange",
           "lemon": "orange", "pear": "apple", "grapes": "cherry", "bug": "ladybug", "insect": "bee", "soap": "block",
           "hands": "hand", "music": "drum", "song": "bell"}


def resolve(name: str) -> str | None:
    n = (name or "").strip().lower().replace(" ", "_")
    if n in ICONS:
        return n
    if n in ALIASES:
        return ALIASES[n]
    if n.endswith("s") and n[:-1] in ICONS:
        return n[:-1]
    for k in ICONS:
        if k in n:
            return k
    return None


@lru_cache(maxsize=512)
def icon(name: str, size: int) -> Image.Image:
    key = resolve(name) or "star"
    im, d = canvas(size, size)
    S = size * SS
    ICONS[key](d, S, max(2, S * 0.03))
    return finish(im)
