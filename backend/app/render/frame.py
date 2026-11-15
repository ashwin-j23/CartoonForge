"""Frame compositor: (timeline, t) -> one picture.

Layout (16:9): the world (set) fills the frame, Sunny the host lives in the top-right sky, up to three friends
stand on the ground. When a learning card is on screen the friends move left and the card takes the right
half (and Sunny moves to the top-left for that segment, so the card never covers him) — one focal point at a
time. Motion is gentle (bob, hop, sway, blink); camera shots never slice a character or card at the frame edge;
segments change with a quick iris wipe (fully closed for a single frame) inside the silent gap between them.
"""
from __future__ import annotations

import bisect
import json
import math
from functools import lru_cache

from PIL import Image, ImageDraw

from ..kids import cast as castmod
from . import expression, palette, sets
from .characters import sprite, shadow
from .common import COLOR_NAMES, COLORS, OUT, darken, ease_in_out, ease_out, ease_out_back, fit_text, font, lighten, rounded, text_img
from .icons import _heart_pts, _star_pts, icon, resolve

ARMS_FOR = {"wave": "wave", "jump": "up", "stretch": "up", "point": "point", "clap": "clap", "dance": "wave",
            "think": "down", "sleep": "down", "idle": "down", "walk": "down"}
CARD_BG = (255, 253, 245)
ACCENTS = [(255, 150, 60), (90, 150, 240), (240, 90, 120), (90, 190, 110), (160, 110, 220)]   # legacy; see palette.py


class Timeline:
    """Everything the compositor needs, picklable for the render workers."""

    def __init__(self, script: dict, audio: dict, W: int, H: int, fps: int, settings: dict):
        ws = 1.5 if settings.get("quality", "high") == "high" else 1.0
        self.out_W, self.out_H = W, H
        self.script, self.W, self.H, self.fps = script, int(W * ws) // 2 * 2, int(H * ws) // 2 * 2, fps
        self.scenes = audio["scenes"]
        self.segments = audio["segments"]
        self.mouth = audio["mouth"]
        self.duration = audio["duration"]
        self.jingle = audio["jingle"]
        self.outro = audio["outro_start"]
        self.starts = [s["start"] for s in self.scenes]
        self.seg_starts = [s["start"] for s in self.segments]
        self.channel = settings.get("channel_name", "Hoppy Hop Hop")
        self.cta = settings.get("cta_line", "") if settings.get("growth_cta", True) else ""
        band = script.get("age_band", "preschool")
        self.captions_all = settings.get("captions_burned", True) and band in ("early", "big")
        self.captions_song = settings.get("captions_burned", True)
        self.title = script.get("title_idea") or script.get("topic", "")
        from ..kids import psychology
        self.pace = psychology.pace(settings.get("_pace") or settings.get("pace"))
        self.band = band
        # colour: one research-based palette per episode (render/palette.py); saturation capped by age
        self.palette = palette.set_current(settings.get("_palette") or palette.choose(script.get("category"), band),
                                           band)
        self.calm_ep = script.get("category") == "bedtime"
        self.vivid = min(float(self.pace["vivid"]), palette.vivid_cap(band))
        self.songs = audio.get("song_regions") or []
        self.storybook = bool(script.get("source"))
        self.guests = {g["id"] for g in script.get("characters") or [] if g.get("id")}
        from .characters import register_guests
        from .styles import set_style
        register_guests(script)
        self.style = set_style(settings.get("_style") or settings.get("art_style"))
        self.ai_bg = dict(settings.get("_bg_images") or {})
        sets.AI_BG.clear()
        sets.AI_BG.update(self.ai_bg)

    def __setstate__(self, state):           # render workers unpickle the timeline: re-register characters + style
        self.__dict__.update(state)
        from .characters import register_guests
        from .styles import set_style
        register_guests(self.script)
        set_style(getattr(self, "style", "classic"))
        palette.set_current(getattr(self, "palette", "rainbow_playground"), getattr(self, "band", "preschool"))
        sets.AI_BG.clear()
        sets.AI_BG.update(getattr(self, "ai_bg", {}))

    def scene_at(self, t: float):
        i = bisect.bisect_right(self.starts, t) - 1
        return (i, self.scenes[i]) if i >= 0 else (-1, None)

    def seg_at(self, t: float):
        i = bisect.bisect_right(self.seg_starts, t) - 1
        return (i, self.segments[i]) if i >= 0 else (-1, None)

    def scene_data(self, sc: dict) -> dict:
        return self.script["segments"][sc["seg"]]["scenes"][sc["idx"]]


# ---------------------------------------------------------------- cards
def _card_key(card: dict) -> str:
    return json.dumps(card, sort_keys=True)


@lru_cache(maxsize=16)
def _card_static(key: str, w: int, h: int) -> Image.Image:
    card = json.loads(key)
    typ = card.get("type")
    acc = palette.on_light(palette.accent(abs(hash(key))))
    panel = rounded(w, h, int(h * .08), CARD_BG, outline=acc, width=max(4, h // 60))
    d = ImageDraw.Draw(panel)
    cx, cy = w / 2, h / 2

    def put(img, x, y):
        panel.alpha_composite(img, (int(x - img.width / 2), int(y - img.height / 2)))

    if typ == "number":
        n = card.get("n", 0)
        put(text_img(str(n), int(h * .55), fill=acc, stroke=OUT, stroke_w=.05), cx, cy - h * .08)
        words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                 "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
        if 0 <= n < len(words):
            put(text_img(words[n].capitalize(), int(h * .12), fill=darken(acc, .2), stroke=None), cx, h * .84)
    elif typ == "letter":
        L = str(card.get("letter") or "A")[:1]
        put(text_img(L.upper() + L.lower(), int(h * .42), fill=acc, stroke=OUT, stroke_w=.04), w * .3, cy - h * .1)
        if card.get("object"):
            put(icon(card["object"], int(h * .38)), w * .72, cy - h * .1)
        word = str(card.get("word") or "")
        if word:
            im = fit_text(word, int(w * .8), int(h * .15), fill=OUT, stroke=None)
            put(im, cx, h * .8)
    elif typ == "word":
        if card.get("object"):
            put(icon(card["object"], int(h * .42)), cx, h * .36)
        put(fit_text(str(card.get("text", ""))[:24], int(w * .85), int(h * .18), fill=acc, stroke=OUT, stroke_w=.06), cx, h * .78)
    elif typ == "color":
        name = str(card.get("color", "red")).lower()
        col = COLORS.get(name, COLORS["red"])
        pts = [(cx + math.cos(a / 20 * math.pi * 2) * h * (.3 + .03 * math.sin(a * 1.7)),
                h * .4 + math.sin(a / 20 * math.pi * 2) * h * (.27 + .03 * math.cos(a * 2.3))) for a in range(20)]
        d.polygon(pts, fill=col, outline=OUT)
        put(text_img(str(card.get("name") or COLOR_NAMES.get(name, name.title())), int(h * .15), fill=col,
                     stroke=OUT if name in ("white", "yellow") else (255, 255, 255), stroke_w=.08), cx, h * .84)
    elif typ == "shape":
        shp = str(card.get("shape", "circle")).lower()
        col = COLORS.get(str(card.get("color", "blue")).lower(), COLORS["blue"])
        r, y = h * .28, h * .4
        lw = max(4, h // 70)
        if shp == "circle":
            d.ellipse([cx - r, y - r, cx + r, y + r], fill=col, outline=OUT, width=lw)
        elif shp == "oval":
            d.ellipse([cx - r * 1.3, y - r * .8, cx + r * 1.3, y + r * .8], fill=col, outline=OUT, width=lw)
        elif shp == "square":
            d.rectangle([cx - r, y - r, cx + r, y + r], fill=col, outline=OUT, width=lw)
        elif shp == "rectangle":
            d.rectangle([cx - r * 1.4, y - r * .75, cx + r * 1.4, y + r * .75], fill=col, outline=OUT, width=lw)
        elif shp == "triangle":
            d.polygon([(cx, y - r), (cx + r * 1.1, y + r * .8), (cx - r * 1.1, y + r * .8)], fill=col, outline=OUT, width=lw)
        elif shp == "diamond":
            d.polygon([(cx, y - r), (cx + r * .8, y), (cx, y + r), (cx - r * .8, y)], fill=col, outline=OUT, width=lw)
        elif shp == "star":
            d.polygon(_star_pts(cx, y, r * 1.1, r * .5), fill=col, outline=OUT, width=lw)
        elif shp == "heart":
            d.polygon(_heart_pts(cx, y, r * 2), fill=col, outline=OUT, width=lw)
        else:
            d.ellipse([cx - r, y - r, cx + r, y + r], fill=col, outline=OUT, width=lw)
        put(text_img(shp.title(), int(h * .14), fill=darken(col, .1), stroke=None), cx, h * .86)
    elif typ == "fact":
        if card.get("object"):
            put(icon(card["object"], int(h * .38)), cx, h * .3)
        _wrap_into(panel, str(card.get("text", "")), w, h, h * .56, int(h * .1))
    elif typ == "page":                         # a line from the book, on a parchment page
        panel = rounded(w, h, int(h * .05), (255, 246, 222), outline=(190, 140, 90), width=max(4, h // 50))
        d = ImageDraw.Draw(panel)
        d.line([(w * .08, h * .12), (w * .92, h * .12)], fill=(220, 190, 150), width=max(2, h // 150))
        if card.get("object"):
            ic = icon(card["object"], int(h * .3))
            panel.alpha_composite(ic, (int(w / 2 - ic.width / 2), int(h * .17)))
        _wrap_into(panel, "“" + str(card.get("text", "")).strip("\"“” ") + "”", w, h, h * .52, int(h * .085))
    elif typ == "question":
        put(text_img("?", int(h * .4), fill=acc, stroke=OUT, stroke_w=.05), cx, h * .3)
        _wrap_into(panel, str(card.get("text", "")), w, h, h * .62, int(h * .11))
    return panel


def _wrap_into(panel, text, w, h, y0, size):
    words, lines, cur = text.split(), [], ""
    f = font(size)
    for wd in words:
        trial = (cur + " " + wd).strip()
        if f.getlength(trial) > w * .86 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    if cur:
        lines.append(cur)
    lines = lines[:3]
    for i, ln in enumerate(lines):
        im = text_img(ln, size, fill=OUT, stroke=None)
        panel.alpha_composite(im, (int(w / 2 - im.width / 2), int(y0 + i * size * 1.15)))


def draw_card(frame: Image.Image, card: dict, sc: dict, t: float, cx: float, cy: float, w: int, h: int, appear_at: float):
    k = ease_out_back((t - appear_at) / 0.4)
    if k <= 0.02:
        return
    panel = _card_static(_card_key(card), w, h)
    if card.get("type") == "count":
        panel = panel.copy() if panel else None
        panel = _count_layer(panel, card, sc, t, w, h)
    if k < 0.999:
        panel = panel.resize((max(1, int(w * k)), max(1, int(h * k))), Image.BILINEAR)
    frame.paste(panel, (int(cx - panel.width / 2), int(cy - panel.height / 2)), panel)


def _count_layer(panel, card, sc, t, w, h):
    n = max(1, min(20, int(card.get("n", 1))))
    reveal = sc.get("reveal") or [sc["start"] + i * 0.3 for i in range(n)]
    cols = min(5, n) if n <= 10 else 5
    rows = math.ceil(n / cols)
    cell = min(w * .86 / cols, h * .68 / rows)
    size = int(cell * .86)
    ic = icon(card.get("object", "star"), size)
    x0 = w / 2 - cols * cell / 2 + cell / 2
    y0 = h * .44 - rows * cell / 2 + cell / 2
    shown = 0
    for i in range(n):
        at = reveal[i] if i < len(reveal) else reveal[-1]
        k = ease_out_back((t - at) / 0.3)
        if k <= 0.02:
            continue
        shown += 1
        im = ic if k > 0.99 else ic.resize((max(1, int(size * k)), max(1, int(size * k))), Image.BILINEAR)
        x = x0 + (i % cols) * cell
        y = y0 + (i // cols) * cell
        panel.alpha_composite(im, (int(x - im.width / 2), int(y - im.height / 2)))
    num = text_img(str(shown), int(h * .16), fill=palette.primary(), stroke=OUT, stroke_w=.06)
    panel.alpha_composite(num, (int(w / 2 - num.width / 2), int(h * .84 - num.height / 2)))
    return panel


# ---------------------------------------------------------------- characters
def _blink(t: float, seed: int) -> bool:
    period = 3.1 + (seed % 5) * 0.37
    return (t + seed * 0.71) % period < 0.13


def _place(frame, cid, x, ground, t, H, *, speaking, mouth, emotion, action, look, appear, seed, energy=1.0, role="",
           changed=None):
    base_h = _base_h(cid, H)
    arms = ARMS_FOR.get(action, "down")
    if action == "dance":
        arms = "wave" if int(t * 2) % 2 else "up"
    elif action == "clap":
        arms = "clap" if int(t * 2.5) % 2 else "down"
    switching = changed is not None and 0 <= t - changed < .09          # blink on an expression change (hides the switch)
    eyes = "closed" if action == "sleep" or emotion == "sleepy" and int(t) % 3 == 0 or _blink(t, seed) or switching \
        else "open"
    emo = "thinking" if action == "think" else emotion
    m = 0 if not speaking else (0 if mouth < .14 else 1 if mouth < .55 else 2)
    look_q = -1 if look < -0.2 else (1 if look > 0.2 else 0)
    del look_q    # (sprites face forward; eyes-follow handled by tilt below to keep the cache small)
    sp = sprite(cid, base_h, m, eyes, emo, arms)
    sx = sy = 1.0
    dy = math.sin(t * 2 * math.pi * (0.7 + 0.35 * (energy - 1)) + seed) * H * .006 * energy
    dx = 0.0
    if action in ("jump",) and speaking:
        ph = (t * 1.6 + seed * .1) % 1
        hop = math.sin(ph * math.pi)
        dy -= hop * H * .07 * min(1.5, energy)
        if ph < .12 or ph > .88:
            sx, sy = 1.08, .92                                   # squash on landing
        else:
            sx, sy = .96, 1.05
    elif action == "dance":
        dx = math.sin(t * math.pi * 1.4 + seed) * H * .02
        dy -= abs(math.sin(t * math.pi * 1.4)) * H * .02
    elif speaking:
        sy = 1 + max(0, mouth) * .025                           # tiny talk bounce
    if speaking:
        sx *= 1.04
        sy *= 1.04
    k = ease_out_back((t - appear) / .45) if appear is not None else 1
    if k <= .02:
        return
    w, h = max(1, int(sp.width * sx * k)), max(1, int(sp.height * sy * k))
    img = sp if (w, h) == sp.size else sp.resize((w, h), Image.BILINEAR)
    if look and not speaking:                                   # lean slightly toward whoever is talking
        img = img.rotate(-look * 3, resample=Image.BILINEAR, expand=False)
    sh = shadow(int(sp.width * .7 * (1 - min(.4, -dy / H * 4))))
    frame.paste(sh, (int(x + dx - sh.width / 2), int(ground - sh.height / 2)), sh)
    frame.paste(img, (int(x + dx - w / 2), int(ground - h + dy + H * .01)), img)
    if role:
        tag = _role_tag(role, H, palette.CURRENT["id"])
        frame.paste(tag, (int(x + dx - tag.width / 2), int(ground - h + dy - tag.height * .2)), tag)


@lru_cache(maxsize=64)
def _role_tag(role: str, H: int, pal: str = ""):
    ti = text_img(role[:22], int(H * .032), fill=(255, 255, 255), stroke=None)
    pill = rounded(ti.width + int(H * .04), int(H * .05), int(H * .025), palette.button(), outline=(255, 255, 255), width=3)
    pill.alpha_composite(ti, ((pill.width - ti.width) // 2, (pill.height - ti.height) // 2))
    return pill


def _sunny_side(tl: Timeline, gi: int) -> str:
    """Sunny lives top-right; in a segment that shows learning cards (they take the right half) he sits top-left
    for the whole segment, so a card never covers him and he never jumps sides mid-segment."""
    cache = tl.__dict__.setdefault("_sunny_side", {})
    if gi not in cache:
        seg = tl.script["segments"][gi] if 0 <= gi < len(tl.script["segments"]) else {}
        cache[gi] = "left" if any(sc.get("card") for sc in seg.get("scenes", [])) else "right"
    return cache[gi]


def _sunny_spot(side: str, big: bool, W: int, H: int) -> tuple[float, float, int]:
    """(centre x, centre y, sprite size) of Sunny before his gentle wobble."""
    size = int(H * (.26 if big else .17))
    x = W * (.115 if side == "left" else .885)
    return x, H * (.2 if big else .15), size


def _sunny(frame, tl: Timeline, t, speaking, mouth, emotion, action, W, H, changed=None, side="right"):
    big = speaking
    x, y, size = _sunny_spot(side, big, W, H)
    m = 0 if not speaking else (0 if mouth < .14 else 1 if mouth < .55 else 2)
    eyes = "closed" if _blink(t, 1) or (changed is not None and 0 <= t - changed < .09) else "open"
    sp = sprite("sunny", size, m, eyes, emotion, "down")
    ang = math.sin(t * .8) * 4
    sp = sp.rotate(ang, resample=Image.BILINEAR)
    x += math.sin(t * .5) * W * .004
    y += math.sin(t * 1.2) * H * .008
    frame.paste(sp, (int(x - sp.width / 2), int(y - sp.height / 2)), sp)


# ---------------------------------------------------------------- captions
def _caption(frame, words, t, W, H, sing):
    if not words:
        return
    # show the current line in chunks of up to 7 words
    idx = max(0, min(len(words) - 1, next((i for i, w in enumerate(words) if w["e"] >= t), len(words) - 1)))
    start = (idx // 7) * 7
    chunk = words[start:start + 7]
    size = int(H * (.072 if sing else .05))
    imgs = []
    for i, w in enumerate(chunk):
        active = w["s"] <= t <= w["e"] + .05
        done = t > w["e"]
        col = palette.highlight() if active else ((255, 255, 255) if done or not sing else (235, 235, 245))
        im = text_img(w["w"], int(size * (1.12 if active and sing else 1)), fill=col, stroke=OUT, stroke_w=.14)
        imgs.append(im)
    gap = size * .3
    total = sum(i.width for i in imgs) + gap * (len(imgs) - 1)
    x = W / 2 - total / 2
    y = H * .9
    bar = rounded(int(total + size * 1.2), int(size * 1.6), int(size * .5), (45, 40, 70, 150))
    frame.paste(bar, (int(W / 2 - bar.width / 2), int(y - bar.height / 2)), bar)
    for im in imgs:
        frame.paste(im, (int(x), int(y - im.height / 2)), im)
        x += im.width + gap


def _banner(frame, title, k, W, H, kind):
    emoji_icon = {"song": "bell", "movement": "ball", "story": "book", "game": "star", "learn": "block", "explore": "plane",
                  "feelings": "heart", "calm": "moon", "recap": "star", "goodbye": "heart", "hello": "sun"}.get(kind, "star")
    t_img = text_img(title, int(H * .065), fill=(255, 255, 255), stroke=OUT, stroke_w=.12)
    ic = icon(emoji_icon, int(H * .09))
    w = t_img.width + ic.width + int(H * .09)
    h = int(H * .12)
    pill = rounded(w, h, h // 2, palette.button(kind in palette.CALM_KINDS), outline=(255, 255, 255), width=max(3, H // 200))
    pill.alpha_composite(ic, (int(H * .03), (h - ic.height) // 2))
    pill.alpha_composite(t_img, (int(H * .05) + ic.width, (h - t_img.height) // 2))
    y = -h + (H * .04 + h) * k
    frame.paste(pill, (int(W / 2 - w / 2), int(y)), pill)


def _countdown(frame, k, cx, cy, r):
    d = ImageDraw.Draw(frame)
    lw = max(4, int(r * .18))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255), outline=(230, 230, 240), width=lw)
    d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * k, fill=palette.accent(1), width=lw)
    q = text_img("?", int(r * 1.2), fill=palette.primary(), stroke=None)
    frame.paste(q, (int(cx - q.width / 2), int(cy - q.height / 2)), q)


def _iris(frame: Image.Image, k: float):
    """k: 0 = fully open, 1 = closed. A soft plum iris, the classic gentle cartoon transition."""
    if k <= 0.01:
        return frame
    W, H = frame.size
    r = math.hypot(W, H) / 2 * (1 - k)
    mask = Image.new("L", (W, H), 255)
    ImageDraw.Draw(mask).ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], fill=0)
    frame.paste((70, 50, 110), (0, 0), mask)
    return frame


def _logo(frame, name, t, W, H, y):
    letters = list(name)
    size = int(H * .12)
    imgs = [text_img(ch, size, fill=palette.accent(i), stroke=(255, 255, 255), stroke_w=.12) if ch != " " else None
            for i, ch in enumerate(letters)]
    total = sum((im.width if im else size * .35) for im in imgs)
    x = W / 2 - total / 2
    for i, im in enumerate(imgs):
        if im is None:
            x += size * .35
            continue
        k = ease_out_back((t - .15 - i * .06) / .5)
        if k > .02:
            bob = math.sin(t * 4 + i * .7) * H * .008
            ii = im if k > .99 else im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))))
            frame.paste(ii, (int(x + im.width / 2 - ii.width / 2), int(y - ii.height / 2 + bob)), ii)
        x += im.width


# ---------------------------------------------------------------- the frame
def _page_turn(frame: Image.Image, k: float) -> Image.Image:
    """Storybook transition: a cream page sweeps across with a soft curled edge. k 0..1 = covered amount."""
    if k <= 0.01:
        return frame
    W, H = frame.size
    x = int(W * (1 - k))
    d = ImageDraw.Draw(frame)
    d.rectangle([x, 0, W, H], fill=(255, 246, 222))
    for i in range(14):                               # curl shadow
        c = 255 - i * 6
        d.line([(x - i, 0), (x - i, H)], fill=(c, c - 12, c - 30), width=1)
    d.line([(x, 0), (x, H)], fill=(200, 160, 110), width=max(2, H // 300))
    return frame


# ---------------------------------------------------------------- camera
# A shot must never slice a character or a card at the frame edge: everything is either fully inside the picture or
# clearly out of it. Each scene knows the bounding box of everything that can be on screen (friends incl. their hops,
# talk-bounce and role tags, Sunny, the card incl. its pop-in overshoot); every shot is framed against those boxes, and
# the in-shot drift / pan / beat punch is clamped per frame so it cannot push an edge back into anything.
Box = tuple  # (x0, y0, x1, y1)

BASE_H = {"hoppy": .9, "pip": .82, "mimi": .95, "bo": 1.12, "zuzu": .95, "nana": .95}


def _base_h(cid: str, H: int) -> int:
    return int(H * .36 * BASE_H.get(cid, .95))


@lru_cache(maxsize=256)
def _sprite_extent(cid: str, base_h: int, style: str) -> tuple[int, int, int, int, int, int]:
    """(canvas w, canvas h, bbox x0, y0, x1, y1) of the character over every arm pose."""
    x0 = y0 = 10 ** 9
    x1 = y1 = 0
    sw = sh = 1
    for arms in ("down", "wave", "up", "point", "clap"):
        sp = sprite(cid, base_h, 0, "open", "happy", arms)
        sw, sh = sp.size
        bb = sp.getbbox() or (0, 0, sw, sh)
        x0, y0, x1, y1 = min(x0, bb[0]), min(y0, bb[1]), max(x1, bb[2]), max(y1, bb[3])
    return sw, sh, x0, y0, x1, y1


def _char_box(cid: str, x: float, ground: float, H: int, energy: float, role: str = "") -> Box:
    """Everything this friend can cover while standing at x: hop, dance sway, talk/squash scale, lean, role tag."""
    from .styles import CURRENT
    sw, sh, bx0, by0, bx1, by1 = _sprite_extent(cid, _base_h(cid, H), CURRENT.get("style", "classic"))
    kx, ky = 1.15, 1.1                                   # squash x talk bounce, plus a little lean
    sway = H * .022
    left = x - sway - (sw / 2 - bx0) * kx
    right = x + sway + (bx1 - sw / 2) * kx
    hop = H * (.07 * min(1.5, energy) + .007 * energy + .021)
    top = ground + H * .01 - (sh - by0) * ky - hop
    if role:
        tw = len(role[:22]) * H * .019 + H * .05
        left, right = min(left, x - tw / 2), max(right, x + tw / 2)
        top -= H * .02
    return left, top, right, ground + H * .03


def _clip(b: Box, W: int, H: int) -> Box:
    return max(0.0, b[0]), max(0.0, b[1]), min(float(W), b[2]), min(float(H), b[3])


def _union(bs) -> Box | None:
    bs = list(bs)
    if not bs:
        return None
    return min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)


def _inside(b: Box, r: Box, eps: float = .5) -> bool:
    return b[0] >= r[0] - eps and b[1] >= r[1] - eps and b[2] <= r[2] + eps and b[3] <= r[3] + eps


def _apart(b: Box, r: Box, eps: float = .5) -> bool:
    return b[2] <= r[0] + eps or b[0] >= r[2] - eps or b[3] <= r[1] + eps or b[1] >= r[3] - eps


def _scene_boxes(tl: Timeline, sc: dict, data: dict, on: list, xs: list, card, speaker: str, side: str,
                 W: int, H: int) -> dict:
    boxes = {}
    roles = data.get("roles") or {}
    ground = H * .93
    for c, xf in zip(on, xs):
        boxes[c] = _clip(_char_box(c, W * xf, ground, H, tl.pace["motion"], str(roles.get(c, ""))), W, H)
    sx, sy, size = _sunny_spot(side, speaker == "sunny", W, H)
    r = size * .53                                        # sprite canvas + rotation/wobble
    boxes["sunny"] = _clip((sx - r - W * .005, sy - r - H * .01, sx + r + W * .005, sy + r + H * .01), W, H)
    if card:
        cw, ch = W * .44 * 1.11 / 2, H * .64 * 1.11 / 2   # pop-in overshoot (ease_out_back)
        boxes["card"] = _clip((W * .69 - cw, H * .47 - ch, W * .69 + cw, H * .47 + ch), W, H)
    return boxes


def _fit_shot(cx: float, cy: float, zd: float, subj: list, boxes: dict, W: int, H: int):
    """Find the framing closest to (cx, cy, zd) that fully contains the subject(s) and leaves every other box either
    fully inside or fully outside. Mild preference for keeping friends in the picture over cutting them out.
    Returns (cx, cy, zoom, U, A): U = union that must stay inside, A = band the crop may pan within."""
    S = _union(boxes[k] for k in subj if k in boxes)
    zs = {1.0, zd}
    for f in (1.06, 1.12, 1.2, 1.3, .94, .88, .82, .76, .7, .64, .58, .52):
        zs.add(zd * f)
    best = None
    for z in sorted(z for z in zs if z >= 1.0):
        w, h = W / z, H / z
        if S and (S[2] - S[0] > w + .5 or S[3] - S[1] > h + .5):
            continue
        lo_x, hi_x = (max(0.0, S[2] - w), min(W - w, S[0])) if S else (0.0, W - w)
        lo_y, hi_y = (max(0.0, S[3] - h), min(H - h, S[1])) if S else (0.0, H - h)
        if lo_x > hi_x + .5 or lo_y > hi_y + .5:
            continue
        want_x = min(max(cx - w / 2, lo_x), hi_x)
        want_y = min(max(cy - h / 2, lo_y), hi_y)
        xs_ = {want_x} | {lo_x + (hi_x - lo_x) * i / 10 for i in range(11)}
        ys_ = {want_y} | {lo_y + (hi_y - lo_y) * i / 4 for i in range(5)}
        for x0 in xs_:
            for y0 in ys_:
                R = (x0, y0, x0 + w, y0 + h)
                inc, out, ok = [], [], True
                for k, b in boxes.items():
                    if _inside(b, R):
                        inc.append(k)
                    elif _apart(b, R):
                        out.append(k)
                    else:
                        ok = False
                        break
                if not ok:
                    continue
                cut = sum(1 for k in out if k not in ("card", "sunny"))
                score = (abs(math.log(z / zd)) * 2 + math.hypot((x0 + w / 2 - cx) / W, (y0 + h / 2 - cy) / H)
                         + .12 * cut)
                if best is None or score < best[0]:
                    best = (score, x0, y0, w, h, z, inc, out)
    if best is None:                                      # the whole world always works
        best = (0, 0.0, 0.0, float(W), float(H), 1.0, list(boxes), [])
    _, x0, y0, w, h, z, inc, out = best
    U = _union(boxes[k] for k in inc)
    # the crop may slide sideways (pan) until it would touch something that was left out
    ax0 = max([0.0] + [boxes[k][2] for k in out if boxes[k][2] <= x0 + .5 and boxes[k][3] > y0 and boxes[k][1] < y0 + h])
    ax1 = min([float(W)] + [boxes[k][0] for k in out if boxes[k][0] >= x0 + w - .5 and boxes[k][3] > y0 and boxes[k][1] < y0 + h])
    A = (ax0, y0, ax1, y0 + h)
    return x0 + w / 2, y0 + h / 2, z, U, A


def _shots(tl: Timeline, si: int, sc: dict, data: dict, on: list, xs: list, card: dict | None, speaker: str, W: int, H: int,
           side: str = "right"):
    """The shot list for this scene: [(start, (name, (cx, cy, zoom), fit))]. Calm = one shot; lively/rapid = cuts.
    Cached per scene (it is the same for every frame of the scene)."""
    cache = tl.__dict__.setdefault("_shot_cache", {})
    key = (si, W, H)
    if key not in cache:
        cache[key] = _plan_shots(tl, si, sc, data, on, xs, card, speaker, W, H, side)
    return cache[key]


def _plan_shots(tl, si, sc, data, on, xs, card, speaker, W, H, side):
    import random as _r
    pc = tl.pace
    end = sc["end"]
    rnd = _r.Random(si * 7919 + 13)
    boxes = _scene_boxes(tl, sc, data, on, xs, card, speaker, side, W, H)
    sp_x = W * xs[on.index(speaker)] if speaker in on else None
    face_y = H * .67                                    # where faces sit (ground .93H, sprites ~.36H tall)
    zmax = pc["zoom"]
    close = min(2.1, zmax * 1.3)
    # (name, framing, subjects, weight). Framings are deliberately far apart so every cut reads as a NEW shot.
    cands = [("wide", (W / 2, H / 2, 1.0), [], 2.0)]
    if sp_x is not None:
        cands.append(("face", (sp_x, face_y, close), [speaker], 3.0))
        cands.append(("speaker", (sp_x, H * .66, zmax), [speaker], 1.5))
    if speaker == "sunny":
        b = boxes["sunny"]
        cands.append(("sunny", ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, min(2.2, close + .2)), ["sunny"], 3.0))
    if card:
        cands.append(("card", (W * .69, H * .47, min(1.45, zmax)), ["card"], 3.0))
    others = [c for c in on if c != speaker]
    if others:
        ox = W * xs[on.index(others[0])]
        cands.append(("react", (ox, face_y, close * .95), [others[0]], 1.6))
    if len(on) >= 2 and not card:
        cands.append(("two", ((W * xs[0] + W * xs[-1]) / 2, H * .7, min(1.35, zmax)), list(on), 1.2))

    fitted = {}

    def frame_of(c):
        if c[0] not in fitted:
            cx, cy, z = c[1]
            fx, fy, fz, U, A = _fit_shot(cx, cy, z, c[2], boxes, W, H)
            fitted[c[0]] = ((fx, fy, fz), (U, A))
        return fitted[c[0]]

    if not pc["shot"]:
        z = 1.0 if sc["kind"] != "question" else 1.06
        f, fit = frame_of(("wide", (W / 2, H / 2, z), [], 1))
        return [(sc["start"], ("wide", f, fit))]
    lo, hi = pc["shot"]
    shots, t, last = [], sc["start"], None
    counting = bool(sc.get("reveal"))
    while t < end - .4:
        if sc["kind"] == "question" and t > sc["voice_end"] - .2:
            pool = [c for c in cands if c[0] in ("card", "wide")] or cands[:1]     # answer pause: show the question
        elif counting and t < (sc["reveal"][-1] + .3):
            pool = [c for c in cands if c[0] in ("card", "wide")]                   # counting: keep objects in view
        else:
            pool = [c for c in cands if c[0] != last] or cands
        pick = rnd.choices(pool, [c[3] for c in pool])[0]
        f, fit = frame_of(pick)
        shots.append((t, (pick[0], f, fit)))
        last = pick[0]
        t += rnd.uniform(lo, hi)
    if not shots:
        f, fit = frame_of(cands[0])
        shots = [(sc["start"], (cands[0][0], f, fit))]
    return shots


def _crop_box(cx: float, cy: float, zoom: float, W: int, H: int, fit=None) -> tuple[float, float, float, float]:
    """(x0, y0, w, h) of the camera crop. With a fit (U, A) the crop keeps U fully inside and stays within A."""
    U, A = fit if fit else (None, None)
    zoom = max(1.0, zoom)
    if A:
        zoom = max(zoom, W / max(1.0, A[2] - A[0]), H / max(1.0, A[3] - A[1]))
    if U:
        zoom = max(1.0, min(zoom, W / max(1.0, U[2] - U[0]), H / max(1.0, U[3] - U[1])))
    w, h = W / zoom, H / zoom
    x0, y0 = cx - w / 2, cy - h / 2
    if A:
        x0 = min(max(x0, A[0]), A[2] - w)
        y0 = min(max(y0, A[1]), A[3] - h)
    if U:
        x0 = min(max(x0, U[2] - w), U[0])
        y0 = min(max(y0, U[3] - h), U[1])
    x0 = min(max(0.0, x0), W - w)
    y0 = min(max(0.0, y0), H - h)
    return x0, y0, w, h


def _camera(img: Image.Image, cx: float, cy: float, zoom: float, W: int, H: int, OW: int | None = None,
            OH: int | None = None, fit=None) -> Image.Image:
    """Crop the world (rendered at W x H, possibly supersampled) and scale it to the output size."""
    OW, OH = OW or W, OH or H
    x0, y0, w, h = _crop_box(cx, cy, zoom, W, H, fit)
    if w >= W - .5 and h >= H - .5 and (OW, OH) == (W, H):
        return img
    return img.resize((OW, OH), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


def _beat_pulse(tl: Timeline, t: float) -> float:
    """Punch-in on the beat during songs (lively/rapid): +4% zoom decaying over a quarter beat."""
    if not tl.pace["shot"]:
        return 0.0
    for r in tl.songs:
        if r["start"] <= t <= r["end"]:
            beat = r.get("beat") or .5
            ph = ((t - r["start"]) % beat) / beat
            return .045 * math.exp(-ph * 6) * (1.0 if int((t - r["start"]) / beat) % 2 == 0 else .55)
    return 0.0


# ---------------------------------------------------------------- transitions
TRANS = .3                                          # seconds to close (and again to open) the iris / page turn


def _switches(tl: Timeline) -> list[tuple[float, bool]]:
    """(time the picture switches content, storybook style?) for every segment boundary and the end card.
    Each switch sits in the middle of the silent gap between segments, so the iris closes over the old segment,
    is fully closed for a single frame, and is open again before the next segment's first word."""
    sw = tl.__dict__.get("_switch_list")
    if sw is None:
        sw = []
        for i in range(len(tl.segments) - 1):
            a, b = tl.segments[i]["end"], tl.segments[i + 1]["start"]
            sw.append(((a + b) / 2, tl.segments[i]["kind"] == "story" or tl.storybook))
        if tl.scenes:
            sw.append((tl.outro, False))
        tl.__dict__["_switch_list"] = sw
    return sw


def _transition(tl: Timeline, t: float) -> tuple[float, bool]:
    """Iris amount at t: 0 open .. 1 closed. Fully closed only for |t - switch| <= half a frame."""
    hold = .5 / tl.fps
    for m, story in _switches(tl):
        d = t - m
        if abs(d) <= hold:
            return 1.0, story
        if -hold - TRANS < d < -hold:                  # ease-in: closes fast at the end, so it is barely blank
            return ((d + hold + TRANS) / TRANS) ** 2, story
        if hold < d < hold + TRANS:                    # and snaps open again right away
            return (1 - (d - hold) / TRANS) ** 2, story
    return 0.0, False


def _lookup_time(tl: Timeline, t: float) -> float:
    """Content time: inside a gap between segments, after the switch point, the next segment is already shown."""
    gi, seg = tl.seg_at(t)
    if seg and gi < len(tl.segments) - 1 and t > seg["end"]:
        nxt = tl.segments[gi + 1]
        if t >= (seg["end"] + nxt["start"]) / 2:
            return nxt["start"]
    return t


# ---------------------------------------------------------------- the frame
@lru_cache(maxsize=4)
def _vignette(W: int, H: int):
    """Soft dark edges (cinematic, pulls the eye to the centre)."""
    small = Image.radial_gradient("L").resize((W // 4, H // 4), Image.BILINEAR)
    small = small.point(lambda v: int(max(0, (v - 150)) * .55))
    return small.resize((W, H), Image.BILINEAR)


def render(tl: Timeline, t: float) -> Image.Image:
    from .styles import frame_fx, set_style, step_time
    style = set_style(getattr(tl, "style", "classic"))
    ts = step_time(t, style)                        # stop-motion looks move 12 times a second
    f = _render(tl, ts)
    k, story = _transition(tl, ts)
    if k > 0.01:
        f = _page_turn(f, k) if story else _iris(f, k)
    if f.size != (tl.out_W, tl.out_H):
        f = f.resize((tl.out_W, tl.out_H), Image.BILINEAR)
    if f.mode != "RGB":
        f = f.convert("RGB")
    f.paste((25, 15, 45), (0, 0), _vignette(tl.out_W, tl.out_H))
    return frame_fx(f, style, t)


def _render(tl: Timeline, t: float) -> Image.Image:
    W, H = tl.W, tl.H
    fi = min(len(tl.mouth) - 1, int(t * tl.fps))
    mouth = float(tl.mouth[fi]) if fi >= 0 else 0.0
    energy = tl.pace["motion"]

    # intro: logo + Sunny + episode title
    if t < tl.jingle - 0.5 or not tl.scenes:
        f = sets.background("storybook" if tl.storybook else "meadow", W, H, tl.vivid).copy()
        sets.overlay(f, "meadow", t, avoid=(.02, .24))      # clouds stay clear of the channel name
        sp = sprite("sunny", int(H * .42), 1 if int(t * 4) % 2 else 2, "open", "excited", "down").rotate(math.sin(t * 3) * 6)
        f.paste(sp, (int(W / 2 - sp.width / 2), int(H * .52 - sp.height / 2 + math.sin(t * 5) * H * .01)), sp)
        # the star hops in beside Sunny for the theme
        if t > .5:
            ph = ((t - .5) * 1.7) % 1
            hop = math.sin(ph * math.pi)
            hp = sprite(castmod.STAR, int(H * .3), 2 if hop > .5 else 1, "open", "excited", "up" if hop > .3 else "wave")
            if ph < .1 or ph > .9:
                hp = hp.resize((int(hp.width * 1.07), int(hp.height * .93)))
            hx = W * .87 - min(1, (t - .5) / .6) * W * .03
            f.paste(hp, (int(hx - hp.width / 2), int(H * .95 - hp.height - hop * H * .08)), hp)
        _logo(f, tl.channel, t, W, H, H * .14)
        k = ease_out((t - 1.2) / .6)
        if k > 0:
            ti = fit_text(tl.title, int(W * .8), int(H * .07), fill=(255, 255, 255), stroke=OUT)
            f.paste(ti, (int(W / 2 - ti.width / 2), int(H * .86 - ti.height / 2 + (1 - k) * H * .1)), ti)
        if tl.pace["shot"]:                                  # energetic intro: slow zoom + beat punch
            f = _camera(f, W / 2, H / 2, 1.0 + .06 * (t / max(1, tl.jingle)) + .03 * abs(math.sin(t * math.pi * 2.1)), W, H)
        return f

    # outro / end card
    if t >= tl.outro:
        lt = t - tl.outro
        f = sets.background("meadow", W, H, tl.vivid).copy()
        sets.overlay(f, "meadow", t, avoid=(.02, .37))      # ...and of the subscribe pill
        for i, cid in enumerate(["pip", "mimi", castmod.STAR, "bo", "zuzu", "nana"]):      # the star in the middle
            x = W * (.1 + i * .16)
            _place(f, cid, x, H * .92, t, H, speaking=False, mouth=0, emotion="happy",
                   action="wave" if (int(t * 1.5) + i) % 2 else "idle", look=0, appear=tl.outro + i * .12, seed=i,
                   energy=energy)
        _logo(f, tl.channel, lt, W, H, H * .14)
        if tl.cta:
            k = ease_out_back((lt - 1.0) / .5)
            if k > .02:
                ci = fit_text(tl.cta, int(W * .7), int(H * .055), fill=(255, 255, 255), stroke=OUT)
                pill = rounded(ci.width + int(H * .2), int(H * .1), int(H * .05), palette.button(), outline=(255, 255, 255), width=4)
                bell = icon("heart", int(H * .07))
                pill.alpha_composite(bell, (int(H * .03), (pill.height - bell.height) // 2))
                pill.alpha_composite(ci, (int(H * .13), (pill.height - ci.height) // 2))
                if k < .99:
                    pill = pill.resize((max(1, int(pill.width * k)), max(1, int(pill.height * k))))
                f.paste(pill, (int(W / 2 - pill.width / 2), int(H * .3 - pill.height / 2)), pill)
        return f

    tq = _lookup_time(tl, t)                     # in a segment gap, past the iris midpoint, show the next segment
    si, sc = tl.scene_at(tq)
    gi, seg = tl.seg_at(tq)
    if sc is None:
        sc, si = tl.scenes[0], 0
    data = tl.scene_data(sc)
    set_id = (seg or {}).get("set") or "meadow"

    speaker = data["speaker"]
    talking = sc["start"] <= t <= sc["voice_end"]
    in_pause = sc["kind"] == "question" and t > sc["voice_end"]
    track = expression.speaker_track(sc, data)               # automatic, word-timed expressions
    emotion, emo_since = expression.at(track, t)

    card = data.get("card")
    appear_at = sc["start"]
    if card:
        j = si
        while j > 0:
            prev = tl.scenes[j - 1]
            if prev["seg"] != sc["seg"] or tl.scene_data(prev).get("card") != card:
                break
            j -= 1
        appear_at = tl.scenes[j]["start"]

    on = [c for c in data.get("cast", []) if (c in castmod.CAST or c in tl.guests) and c != "sunny"][:3] or [castmod.STAR]
    roles = data.get("roles") or {}
    ground = H * .93
    xs = ({1: [.2], 2: [.13, .31], 3: [.09, .22, .35]} if card else {1: [.5], 2: [.36, .64], 3: [.27, .5, .73]})[len(on)]
    sx_speaker = xs[on.index(speaker)] if speaker in on else ((.115 if _sunny_side(tl, sc["seg"]) == "left" else .885) if speaker == "sunny" else .5)

    # camera shot first: close-ups get a softly blurred background (depth of field), like a real lens
    side = _sunny_side(tl, sc["seg"])
    shots = _shots(tl, si, sc, data, on, xs, card, speaker, W, H, side)
    k = max(0, bisect.bisect_right([s[0] for s in shots], t) - 1)
    name, (cx, cy, z), fit = shots[k][1]
    dof = z >= 1.3 and name in ("face", "react", "speaker", "sunny")
    calm = tl.calm_ep or (seg or {}).get("kind") in palette.CALM_KINDS
    vivid = palette.vivid_cap(tl.band, True) if calm else tl.vivid
    f = (sets.background_blur(set_id, W, H, vivid, calm) if dof else sets.background(set_id, W, H, vivid, calm)).copy()
    sets.overlay(f, set_id, t)
    for c, xf in zip(on, xs):
        j = si
        while j > 0 and tl.scenes[j - 1]["seg"] == sc["seg"] and c in tl.scene_data(tl.scenes[j - 1]).get("cast", []):
            j -= 1
        first = tl.scenes[j]["start"] if tl.scenes[j]["seg"] == sc["seg"] else sc["start"]
        is_sp = c == speaker
        c_emo, c_since = (emotion, emo_since) if is_sp else expression.listener(track, sc, t, hash(c) % 7, in_pause)
        _place(f, c, W * xf, ground, t, H, speaking=is_sp and talking, mouth=mouth if is_sp else 0,
               emotion=c_emo, changed=c_since,
               action=data.get("action", "idle") if is_sp else ("dance" if data.get("action") == "dance" else "idle"),
               look=0 if is_sp else (1 if sx_speaker > xf else -1), appear=first if first > seg["start"] + .01 else None,
               seed=hash(c) % 7, energy=energy, role=str(roles.get(c, ""))[:22])

    s_emo, s_since = (emotion, emo_since) if speaker == "sunny" else expression.listener(track, sc, t, 1, in_pause)
    _sunny(f, tl, t, speaker == "sunny" and talking, mouth, s_emo, data.get("action", "idle"), W, H, s_since, side)
    if card:
        draw_card(f, card, sc, t, W * .69, H * .47, int(W * .44), int(H * .64), appear_at)

    # ---- camera: drift inside the shot, punch on the beat
    s_start = shots[k][0]
    s_end = shots[k + 1][0] if k + 1 < len(shots) else sc["end"]
    prog = min(1.0, max(0.0, (t - s_start) / max(.3, s_end - s_start)))
    drift = (.05 if tl.pace["shot"] else .04) * ease_in_out(prog)
    pan = (W * .015 if (k + si) % 2 else -W * .015) * (prog - .5) if name != "wide" else 0
    zoom = z + drift + _beat_pulse(tl, t)
    if name == "wide" and not tl.pace["shot"] and sc["kind"] != "question":
        zoom = 1.0
    f = _camera(f, cx + pan, cy, zoom, W, H, tl.out_W, tl.out_H, fit)
    W, H = tl.out_W, tl.out_H                     # HUD is drawn at output size, crisp, never cropped

    # ---- HUD (never cropped by the camera)
    if in_pause:
        kk = (t - sc["voice_end"]) / max(.1, sc["end"] - sc["voice_end"])
        _countdown(f, kk, W * .5 if not card else W * .69, H * .13, H * .06)
    if sc.get("sing") and tl.captions_song:
        _caption(f, sc["words"], t, W, H, True)
    elif tl.captions_all and talking:
        _caption(f, sc["words"], t, W, H, False)
    if seg:
        lt = t - seg["start"]
        if 0.3 < lt < 3.2 and seg["kind"] not in ("hello",):
            kb = ease_out((lt - .3) / .5) if lt < 2.6 else 1 - ease_in_out((lt - 2.6) / .6)
            _banner(f, seg["title"], kb, W, H, seg["kind"])
    return f
