"""The cast, drawn in code.

Design rules from the psychology playbook: big heads and big eyes (baby schema), round shapes, warm colours,
soft outline, one strong silhouette per character so a 2-year-old can tell them apart at a glance.

The look ("show bible"):
  * line weight: a bold plum contour around every form, thinner interior lines, tapered strokes for brows,
    closed eyes and smiles;
  * shading: every form gets a cool-violet form shadow (lower right), a warm rim light (upper left) and the head
    casts a soft contact shadow on the body; eyes get a sclera shadow, a two-tone iris and two speculars;
  * acting: 9 emotions drive lids, brows, pupils, mouth shape and (where the species has them) ears.

sprite(char, height, mouth, eyes, emotion, arms) -> RGBA. Variants are cached; per-frame motion (bob, squash
and stretch, hop, sway) is applied by the compositor, so drawing cost is paid once per variant.
"""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..kids.cast import CAST
from .common import OUT, SS, canvas, darken, lighten

EMOTIONS = ("happy", "excited", "surprised", "thinking", "sad", "worried", "proud", "sleepy", "calm")
ARMS = ("down", "wave", "up", "point", "clap")

SHADOW_TINT = (92, 58, 150, 255)      # blended over a form = cool violet form shadow
RIM_TINT = (255, 250, 236, 255)       # warm rim light
OUTA = OUT + (255,)
EYE_INK = (38, 28, 56)
MOUTH_DARK = (112, 38, 66)
TONGUE = (255, 128, 150)
BLUSH = (255, 120, 140)


def shadow_tint(col=None):
    """Cool violet shadows for most colours; warm sienna for yellows/oranges (violet over yellow turns muddy)."""
    if col is not None:
        r, g, b = col[:3]
        if r > 200 and g > 110 and b < 140 and r - b > 100:
            return (205, 95, 70, 255)
    return SHADOW_TINT


def _mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _bez(ctrl, n=14):
    """Points along a linear / quadratic / cubic Bezier given by 2-4 control points."""
    out = []
    for i in range(n + 1):
        t = i / n
        m = 1 - t
        if len(ctrl) == 4:
            (a, b), (c, d), (e, f), (g, h) = ctrl
            out.append((m ** 3 * a + 3 * m * m * t * c + 3 * m * t * t * e + t ** 3 * g,
                        m ** 3 * b + 3 * m * m * t * d + 3 * m * t * t * f + t ** 3 * h))
        elif len(ctrl) == 3:
            (a, b), (c, d), (e, f) = ctrl
            out.append((m * m * a + 2 * m * t * c + t * t * e, m * m * b + 2 * m * t * d + t * t * f))
        else:
            (a, b), (c, d) = ctrl[0], ctrl[-1]
            out.append((a + (c - a) * t, b + (d - b) * t))
    return out


# ================================================================= toon kit
class Toon:
    """Drawing kit in 'units': the sprite is 100 units tall, x is measured from the centre line.

    Shapes are ('e', cx, cy, rx, ry) or ('p', points) in pixels; constructors take units."""

    def __init__(self, d: ImageDraw.ImageDraw, W: float, H: float):
        self.d, self.im = d, d._image
        self.W, self.H = W, H
        self.u = H / 100.0
        self.cx = W / 2
        self.lw = max(2.0, H * .0105)          # outer contour
        self.li = max(1.5, H * .0060)          # interior lines

    # ---- coordinates + shapes
    def P(self, x, y):
        return (self.cx + x * self.u, y * self.u)

    def E(self, x, y, rx, ry):
        return ("e", self.cx + x * self.u, y * self.u, rx * self.u, ry * self.u)

    def poly(self, pts):
        return ("p", [self.P(x, y) for x, y in pts])

    def egg(self, x, y, rx, ry, top=.85, bot=1.0, n=60):
        """Ellipse that is narrower (top<1) or wider at the top than the bottom: heads, bodies, pears."""
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            c, s = math.cos(a), math.sin(a)
            k = bot + (top - bot) * (1 - s) / 2
            pts.append((x + rx * c * k, y + ry * s))
        return self.poly(pts)

    def blob(self, x, y, rx, ry, bumps=None, n=72):
        """Ellipse with radius modulation: bumps = [(angle_deg, width_deg, amount), ...] (amount in fraction)."""
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            k = 1.0
            for ang, wid, amt in bumps or ():
                da = (math.degrees(a) - ang + 180) % 360 - 180
                if abs(da) < wid:
                    k += amt * (1 - abs(da) / wid) ** 1.5
            pts.append((x + rx * k * math.cos(a), y + ry * k * math.sin(a)))
        return self.poly(pts)

    def scallop(self, x, y, rx, ry, n=14, depth=.12, phase=0.0, steps=6):
        """Cloud / mane / wool outline: n round bumps around an ellipse."""
        pts = []
        for i in range(n * steps):
            a = 2 * math.pi * i / (n * steps) + phase
            f = (i % steps) / steps
            k = 1 + depth * math.sin(math.pi * f) - depth * .5
            pts.append((x + rx * k * math.cos(a), y + ry * k * math.sin(a)))
        return self.poly(pts)

    def rot_ell(self, x, y, rx, ry, ang, n=32):
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        pts = []
        for i in range(n):
            t = 2 * math.pi * i / n
            ex, ey = rx * math.cos(t), ry * math.sin(t)
            pts.append((x + ex * ca - ey * sa, y + ex * sa + ey * ca))
        return self.poly(pts)

    def tube_pts(self, path, radii):
        """Outline of a stroke of varying radius along a path (units in, units out), with round caps."""
        n = len(path)
        if n < 2:
            path = [path[0], (path[0][0] + .01, path[0][1])]
            n = 2

        def r_at(i):
            pos = i / (n - 1) * (len(radii) - 1)
            j = min(int(pos), len(radii) - 2)
            f = pos - j
            return radii[j] * (1 - f) + radii[j + 1] * f

        left, right, normals = [], [], []
        for i in range(n):
            p0, p1 = path[max(0, i - 1)], path[min(n - 1, i + 1)]
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            ln = math.hypot(dx, dy) or 1e-6
            nx, ny = -dy / ln, dx / ln
            r = r_at(i)
            left.append((path[i][0] + nx * r, path[i][1] + ny * r))
            right.append((path[i][0] - nx * r, path[i][1] - ny * r))
            normals.append(math.atan2(ny, nx))
        cap_e, cap_s = [], []
        r1, r0 = r_at(n - 1), r_at(0)
        for j in range(1, 8):
            a = normals[-1] - math.pi * j / 8
            cap_e.append((path[-1][0] + math.cos(a) * r1, path[-1][1] + math.sin(a) * r1))
            a = normals[0] + math.pi - math.pi * j / 8
            cap_s.append((path[0][0] + math.cos(a) * r0, path[0][1] + math.sin(a) * r0))
        return left + cap_e + right[::-1] + cap_s

    def tube(self, path, radii):
        return self.poly(self.tube_pts(path, radii))

    # ---- raw drawing
    @staticmethod
    def bbox(sh):
        if sh[0] == "e":
            _, x, y, rx, ry = sh
            return x - rx, y - ry, x + rx, y + ry
        xs = [p[0] for p in sh[1]]
        ys = [p[1] for p in sh[1]]
        return min(xs), min(ys), max(xs), max(ys)

    def draw_shape(self, dr, sh, fill, ox=0.0, oy=0.0, grow=0.0, scale=1.0):
        if sh[0] == "e":
            _, x, y, rx, ry = sh
            rx, ry = rx * scale + grow, ry * scale + grow
            if rx > 0 and ry > 0:
                dr.ellipse([x + ox - rx, y + oy - ry, x + ox + rx, y + oy + ry], fill=fill)
            return
        pts = sh[1]
        if scale != 1.0:
            x0, y0, x1, y1 = self.bbox(sh)
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            pts = [(mx + (px - mx) * scale, my + (py - my) * scale) for px, py in pts]
        if ox or oy:
            pts = [(px + ox, py + oy) for px, py in pts]
        dr.polygon(pts, fill=fill)
        if grow > 0:
            dr.line(pts + pts[:2], fill=fill, width=max(1, int(round(grow * 2))), joint="curve")

    def ink(self, sh, w=None):
        self.draw_shape(self.d, sh, OUT, grow=self.lw if w is None else w)

    def fill(self, sh, col):
        self.draw_shape(self.d, sh, tuple(col[:3]))

    def part(self, sh, col, w=None, shade=None):
        """Inked + filled form; shade=(shadow, rim) applies form lighting right away."""
        if w is None or w > 0:
            self.ink(sh, w)
        self.fill(sh, col)
        if shade:
            self.form(sh, *shade, col=col)
        return sh

    def group(self, shapes, col, w=None, shade=None):
        """Several overlapping shapes read as ONE form: one outer contour, no inner lines."""
        for sh in shapes:
            self.ink(sh, w)
        for sh in shapes:
            self.fill(sh, col)
        if shade:
            for sh in shapes:
                self.form(sh, *shade, col=col)

    def _mask(self, sh, pad=2):
        x0, y0, x1, y1 = self.bbox(sh)
        x0, y0 = max(0, int(x0) - pad), max(0, int(y0) - pad)
        x1, y1 = min(self.im.width, int(x1) + pad + 1), min(self.im.height, int(y1) + pad + 1)
        if x1 - x0 < 3 or y1 - y0 < 3:
            return None, None
        m = Image.new("L", (x1 - x0, y1 - y0), 0)
        return m, (x0, y0, x1, y1)

    def form(self, sh, shadow=.30, rim=.45, depth=.2, col=None, tint=None):
        """Light the form: violet core shadow on the lower right, warm rim light on the upper left.
        Applies to everything already drawn inside the shape (patches, spots...)."""
        m, box = self._mask(sh)
        if m is None:
            return
        md = ImageDraw.Draw(m)
        size = min(box[2] - box[0], box[3] - box[1])
        x0, y0 = box[0], box[1]
        if shadow:
            s = size * depth
            self.draw_shape(md, sh, int(255 * shadow), -x0, -y0)
            self.draw_shape(md, sh, 0, -x0 - s * .55, -y0 - s * .85, scale=1.04)
            self.im.paste(tint or shadow_tint(col), box, m)
        if rim:
            m.paste(0, (0, 0, m.width, m.height))
            r = max(2.0, size * .05)
            self.draw_shape(md, sh, int(255 * rim), -x0, -y0)
            self.draw_shape(md, sh, 0, -x0 + r * .55, -y0 + r)
            self.im.paste(RIM_TINT, box, m)

    def occlude(self, onto, caster, dy=2.5, dx=0.0, k=.32):
        """Soft contact shadow that `caster` (drawn afterwards) casts onto `onto`."""
        m, box = self._mask(onto)
        if m is None:
            return
        md = ImageDraw.Draw(m)
        self.draw_shape(md, onto, int(255 * k), -box[0], -box[1])
        c = Image.new("L", m.size, 0)
        self.draw_shape(ImageDraw.Draw(c), caster, 255, -box[0] + dx * self.u, -box[1] + dy * self.u)
        self.im.paste(SHADOW_TINT, box, ImageChops.darker(m, c))

    def glaze(self, sh, col, alpha):
        """Translucent colour over a shape (lens tint, cheek blush without blur, wing membranes)."""
        m, box = self._mask(sh)
        if m is None:
            return
        self.draw_shape(ImageDraw.Draw(m), sh, int(255 * alpha), -box[0], -box[1])
        self.im.paste(tuple(col[:3]) + (255,), box, m)

    def clip_paste(self, clip, sh, col, alpha=1.0):
        """Fill `sh` with col, but only inside `clip`."""
        m, box = self._mask(clip)
        if m is None:
            return
        self.draw_shape(ImageDraw.Draw(m), clip, 255, -box[0], -box[1])
        s = Image.new("L", m.size, 0)
        self.draw_shape(ImageDraw.Draw(s), sh, int(255 * alpha), -box[0], -box[1])
        self.im.paste(tuple(col[:3]) + (255,), box, ImageChops.darker(m, s))

    def blush(self, x, y, rx, ry, col=BLUSH, alpha=.55):
        sh = self.E(x, y, rx, ry)
        m, box = self._mask(sh, pad=int(rx * self.u * .5) + 2)
        if m is None:
            return
        self.draw_shape(ImageDraw.Draw(m), sh, int(255 * alpha), -box[0], -box[1])
        small = m.resize((max(1, m.width // 4), max(1, m.height // 4)), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(max(1, rx * self.u * .1)))
        self.im.paste(tuple(col[:3]) + (255,), box, small.resize(m.size, Image.BILINEAR))
        # two tiny shine dots make the blush read as a rosy cheek, not a smudge
        self.fill(self.E(x - rx * .35, y - ry * .2, rx * .12, rx * .12), lighten(col, .6))

    def stroke(self, path, width, col=OUT, taper=(.35, 1.0, .35)):
        """Tapered brush stroke along a path (units): brows, closed eyes, smiles, feather marks."""
        radii = [width * t / 2 for t in taper]
        self.fill(self.tube(path, radii), col)


# ================================================================= faces
#        h-scale up-lid tilt lo-lid iris pupil look
EYE = {
    "happy":     (1.00, .00, 0.0, .17, 1.00, 1.00, (0, 0)),
    "excited":   (1.08, .00, 0.0, .10, 1.06, 1.00, (0, -.15)),
    "surprised": (1.18, .00, 0.0, .00, .80, .66, (0, 0)),
    "thinking":  (1.06, .00, 0.0, .04, .96, .96, (.95, -1.25)),   # wide open, gazing up and to the side: "hmm, I wonder…"
    "sad":       (.98, .30, .90, .06, 1.02, 1.08, (0, .55)),
    "worried":   (1.06, .10, .60, .06, .92, .84, (0, .2)),
    "proud":     (1.00, .30, 0.0, .20, 1.00, 1.00, (0, 0)),
    "sleepy":    (.96, .36, 0.0, .24, 1.00, 1.00, (0, .2)),      # heavy but rounded lids + soft smile: sweet, not bored
    "calm":      (1.00, .08, 0.0, .26, 1.00, 1.00, (0, 0)),       # smiling eyes (lower lids up), never half-lidded
}
#        inner-dy outer-dy arch raise   (in eye-heights; negative = up)
BROW = {
    "happy":     (.00, .06, .26, .00),
    "excited":   (-.12, -.04, .36, -.38),
    "surprised": (-.10, -.04, .46, -.62),
    "thinking":  (-.02, .04, .24, -.08),      # relaxed, slightly lifted; the other brow arches high (see _brow)
    "sad":       (-.42, .22, -.04, -.08),
    "worried":   (-.52, .24, .10, -.16),
    "proud":     (.06, -.12, .26, -.18),
    "sleepy":    (-.10, .14, .26, -.10),      # soft, lifted at the inner end: droopy-sweet, never frowning
    "calm":      (-.04, .06, .30, -.10),      # gently raised, rounded
}
#        curve shape open-scale
MOUTH = {
    "happy": (.55, "smile", 1.0), "excited": (.78, "smile", 1.18), "surprised": (0, "o", 1.0),
    "thinking": (.3, "side", .8), "sad": (-.5, "frown", .8), "worried": (-.25, "wobble", .85),
    "proud": (.68, "smile", .95), "sleepy": (.34, "yawn", .9), "calm": (.48, "smile", .85),
}


def eye(k: Toon, x, y, s, sx, eyes, emo, iris=(70, 50, 90), lash=False, look_extra=(0, 0), brow_col=None,
        brow=True, wide=.8):
    """One big friendly eye at (x, y), s = half-height (units). sx = -1 left eye / +1 right eye."""
    hs, up, tilt, lo, isc, psc, look = EYE.get(emo, EYE["happy"])
    look = (look[0] + look_extra[0], look[1] + look_extra[1])
    u = k.u
    if brow:
        _brow(k, x, y, s, sx, emo, brow_col or OUT)
    if eyes == "closed" or emo == "proud":
        rx = s * wide
        if emo == "proud" and eyes != "closed":      # happy ^ ^ eyes
            path = _bez([(x - rx * .95, y + s * .3), (x, y - s * .85), (x + rx * .95, y + s * .3)], 12)
        else:                                       # relaxed closed lid
            path = _bez([(x - rx, y + s * .05), (x, y + s * .7), (x + rx, y + s * .05)], 12)
        k.stroke(path, s * .36, OUT, (.4, 1, .55))
        if lash:
            ox, oy = x + sx * rx * .95, y + s * .05
            k.stroke([(ox, oy), (ox + sx * s * .35, oy - s * .3)], s * .2, OUT, (1, .7, .2))
        return
    ry = s * hs
    rx = s * wide
    px0, py0 = k.P(x, y)
    RX, RY = rx * u, ry * u
    g = k.li * 1.1
    pad = int(g * 3 + 4)
    bx0, by0 = int(px0 - RX - pad), int(py0 - RY - pad)
    w, h = int(2 * RX + 2 * pad), int(2 * RY + 2 * pad)
    ex, ey = px0 - bx0, py0 - by0
    A = Image.new("L", (w, h), 0)
    I = Image.new("L", (w, h), 0)
    ad, idr = ImageDraw.Draw(A), ImageDraw.Draw(I)
    ad.ellipse([ex - RX, ey - RY, ex + RX, ey + RY], fill=255)
    idr.ellipse([ex - RX - g, ey - RY - g, ex + RX + g, ey + RY + g], fill=255)
    xs = [ex - RX - g * 2 + i * (2 * RX + g * 4) / 15 for i in range(16)]
    if up > 0:
        def yu(xx):
            f = (xx - ex) / RX
            arc = {"sleepy": -.6, "calm": -.3}.get(emo, .1)   # domed (content) lid for sleepy/calm, flat otherwise
            return ey - RY + up * 2 * RY + tilt * sx * f * RY * .4 + (1 - min(1, f * f)) * RY * arc
        edge = [(xx, yu(xx)) for xx in xs]
        ad.polygon(edge + [(xs[-1], -5), (xs[0], -5)], fill=0)
        idr.polygon([(a, b - g) for a, b in edge] + [(xs[-1], -5), (xs[0], -5)], fill=0)
    if lo > 0:
        def yl(xx):
            f = (xx - ex) / RX
            return ey + RY - 2 * lo * RY * (1 - .55 * min(1, f * f))
        edge = [(xx, yl(xx)) for xx in xs]
        ad.polygon(edge + [(xs[-1], h + 5), (xs[0], h + 5)], fill=0)
        idr.polygon([(a, b + g) for a, b in edge] + [(xs[-1], h + 5), (xs[0], h + 5)], fill=0)
    box = (bx0, by0, bx0 + w, by0 + h)
    k.im.paste(OUTA, box, I)
    L = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    ld = ImageDraw.Draw(L)
    ld.ellipse([ex - RX * 1.3, ey - RY * 2.0, ex + RX * 1.3, ey - RY * .45], fill=(222, 225, 242, 255))
    ir = RX * .78 * isc
    iry = ir * 1.13
    ix = ex + look[0] * RX * .3
    iy = ey + RY * .1 + look[1] * RY * .28
    ld.ellipse([ix - ir, iy - iry, ix + ir, iy + iry], fill=tuple(iris[:3]) + (255,))
    ld.ellipse([ix - ir * .78, iy - iry * .05, ix + ir * .78, iy + iry * .92], fill=lighten(iris, .28) + (255,))
    ld.ellipse([ix - ir, iy - iry, ix + ir, iy + iry], outline=darken(iris, .45) + (255,), width=max(1, int(ir * .1)))
    pr = ir * .56 * psc
    ld.ellipse([ix - pr, iy - pr * 1.08, ix + pr, iy + pr * 1.08], fill=EYE_INK + (255,))
    hr = ir * (.42 if emo != "sad" else .5)
    hx, hy = ix - ir * .3, iy - iry * .4
    ld.ellipse([hx - hr, hy - hr * 1.05, hx + hr, hy + hr * 1.05], fill=(255, 255, 255, 255))
    sr = ir * .17
    ld.ellipse([ix + ir * .42 - sr, iy + iry * .42 - sr, ix + ir * .42 + sr, iy + iry * .42 + sr], fill=(255, 255, 255, 235))
    if emo == "excited":                              # star sparkle
        cxs, cys, a, b = ix + ir * .45, iy - iry * .25, ir * .32, ir * .08
        ld.polygon([(cxs, cys - a), (cxs + b, cys - b), (cxs + a, cys), (cxs + b, cys + b), (cxs, cys + a),
                    (cxs - b, cys + b), (cxs - a, cys), (cxs - b, cys - b)], fill=(255, 255, 255, 255))
    k.im.paste(L, box, A)
    As = Image.new("L", (w, h), 0)
    As.paste(A, (0, int(g * 1.5)))
    k.im.paste(OUTA, box, ImageChops.subtract(A, As))          # thicker upper lash line, tapers at corners
    if lash:
        top_y = y - ry + (up * 2 * ry if up else 0)
        for j, (dx, ln) in enumerate(((.62, .42), (.9, .36))):
            ox = x + sx * rx * dx
            oy = top_y + ry * (.15 + j * .28) + up * ry * .2
            k.stroke([(ox, oy), (ox + sx * s * ln * .8, oy - s * ln * .7)], s * .17, OUT, (1, .7, .15))


def _brow(k, x, y, s, sx, emo, col):
    din, dout, arch, rise = BROW.get(emo, BROW["happy"])
    if emo == "thinking" and sx > 0:
        din, dout, arch, rise = -.06, -.22, .5, -.72        # ONE brow arched high: curious, not suspicious
    by = y - s * 1.62 + rise * s
    a = (x - sx * s * .55, by + din * s)
    b = (x + sx * s * .78, by + dout * s)
    c = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - arch * s)
    k.stroke(_bez([a, c, b], 10), s * .34, col, (.85, 1, .3))


def mouth_shape(k: Toon, x, y, hw, mouth, emo):
    """Unit-space polygon of an open mouth (None when closed)."""
    curve, shape, osc = MOUTH.get(emo, MOUTH["happy"])
    if mouth <= 0:
        return None
    oh = hw * (.55 if mouth == 1 else 1.0) * osc
    if shape == "o":
        rx, ry = hw * (.32 if mouth == 1 else .42), oh * .62
        return [(x + rx * math.cos(a), y + ry * .4 + ry * math.sin(a)) for a in [2 * math.pi * i / 28 for i in range(28)]]
    if shape == "yawn":
        rx, ry = hw * .45, oh * .55
        return [(x + rx * math.cos(a), y + ry * .5 + ry * math.sin(a)) for a in [2 * math.pi * i / 28 for i in range(28)]]
    L = curve * hw * .45
    ft, fb = (.1, .9) if curve >= 0 else (.55, .45)
    hwo = hw * (.82 if mouth == 1 else .92)
    off = hw * .18 if shape == "side" else 0
    top, bot = [], []
    for i in range(17):
        t = -1 + i / 8
        xx = x + off + t * hwo
        yc = y - L * t * t + (t * hw * .12 if shape == "side" else 0)
        bulge = (1 - t * t) ** .8
        wob = math.sin(t * math.pi * 2) * oh * .07 if shape == "wobble" else 0
        top.append((xx, yc - oh * ft * bulge + wob))
        bot.append((xx, yc + oh * fb * bulge))
    return top + bot[::-1]


def mouth(k: Toon, x, y, hw, mouth, emo, teeth=False, buck=False, tongue=TONGUE):
    """Expressive mouth centred at (x, y) with half-width hw (units). mouth: 0 closed, 1 half, 2 open."""
    curve, shape, _ = MOUTH.get(emo, MOUTH["happy"])
    if mouth <= 0:
        L = curve * hw * .45
        if shape == "o":
            k.part(k.E(x, y + hw * .1, hw * .2, hw * .24), MOUTH_DARK, k.li)
        elif shape == "wobble":
            pts = [(x + t * hw * .75, y + math.sin(t * math.pi * 2) * hw * .1 + hw * .05) for t in [-1 + i / 8 for i in range(17)]]
            k.stroke(pts, hw * .17, OUT, (.6, 1, .6))
        elif shape == "side":
            k.stroke(_bez([(x - hw * .3, y + hw * .1), (x + hw * .2, y + hw * .12), (x + hw * .62, y - hw * .14)], 10),
                     hw * .17, OUT, (.5, 1, .45))
        else:
            ww = hw * (.85 if abs(curve) > .3 else .55)
            pts = [(x + t * ww, y - L * t * t) for t in [-1 + i / 8 for i in range(17)]]
            k.stroke(pts, hw * .18, OUT, (.45, 1, .45))
            if curve >= .5:                             # dimples at the corners sell the smile
                for sx in (-1, 1):
                    cx_, cy_ = x + sx * ww, y - L
                    k.stroke([(cx_ - sx * hw * .12, cy_ - hw * .14), (cx_ + sx * hw * .06, cy_ + hw * .1)], hw * .1, OUT, (.3, 1, .3))
            if buck:
                k.part(k.poly([(x - hw * .2, y - L * 0 + hw * .06), (x + hw * .2, y + hw * .06),
                               (x + hw * .18, y + hw * .38), (x - hw * .18, y + hw * .38)]), (255, 255, 255), k.li * .8)
                k.stroke([(x, y + hw * .08), (x, y + hw * .36)], hw * .05, OUT, (1, 1, 1))
        return
    pts = mouth_shape(k, x, y, hw, mouth, emo)
    sh = k.poly(pts)
    k.part(sh, MOUTH_DARK, k.li * 1.1)
    ys = [p[1] for p in pts]
    ytop, ybot = min(ys), max(ys)
    oh = ybot - ytop
    k.clip_paste(sh, k.E(x, ybot - oh * .12, hw * .5, oh * .38), tongue)
    if teeth and curve > 0 and shape in ("smile",):
        k.clip_paste(sh, k.poly([(x - hw, ytop - 2), (x + hw, ytop - 2), (x + hw, ytop + oh * .2), (x - hw, ytop + oh * .2)]),
                     (255, 255, 255))
    if buck:
        k.clip_paste(sh, k.poly([(x - hw * .22, ytop - 1), (x + hw * .22, ytop - 1), (x + hw * .2, ytop + oh * .34),
                                 (x - hw * .2, ytop + oh * .34)]), (255, 255, 255))
        k.stroke([(x, ytop), (x, ytop + oh * .32)], hw * .045, OUT, (1, 1, 1))


def nose(k: Toon, x, y, w, col=(62, 44, 62)):
    """Soft rounded-triangle nose with a shine."""
    pts = _bez([(x - w, y - w * .35), (x, y - w * .75), (x + w, y - w * .35)], 8) + \
        _bez([(x + w, y - w * .35), (x + w * .55, y + w * .65), (x, y + w * .6)], 6)[1:] + \
        _bez([(x, y + w * .6), (x - w * .55, y + w * .65), (x - w, y - w * .35)], 6)[1:]
    k.part(k.poly(pts), col, k.li * .9)
    k.fill(k.E(x - w * .3, y - w * .25, w * .32, w * .17), lighten(col, .55))


# ================================================================= arms
#              hand target (x along L, outward +), elbow bend
POSES = {"down": ((.34, .95), (.14, .05)), "wave": ((.92, -.72), (.3, .14)), "up": ((.5, -.86), (.3, .08)),
         "point": ((1.0, -.1), (.05, .14)), "clap": (None, (.18, .26))}


def _arm_angles(arms: str) -> tuple[float, float]:
    """(left, right) angles - kept for older callers."""
    return {"down": (25, 25), "wave": (25, 150), "up": (160, 160), "point": (25, 95), "clap": (60, 60)}.get(arms, (25, 25))


def side_pose(arms: str, sx: int) -> str:
    if arms in ("wave", "point") and sx < 0:
        return "down"
    return arms


def limb(k: Toon, sx, shoulder, L, r, col, pose, kind="paw", hand_col=None, clap_x=2.5, w=None):
    """An arm / flipper / wing from `shoulder` (units). kind: paw | hand | flipper | wing."""
    sxp, syp = shoulder
    tgt, bend = POSES.get(pose, POSES["down"])
    if pose == "clap":
        hx, hy = sx * clap_x, syp + L * .55
    else:
        hx, hy = sxp + sx * tgt[0] * L, syp + tgt[1] * L
    lim = k.W / (2 * k.u) - r * 1.9 - 1
    if abs(hx) > lim:
        hx = math.copysign(lim, hx)
    mx, my = (sxp + hx) / 2 + sx * bend[0] * L, (syp + hy) / 2 + bend[1] * L
    path = _bez([(sxp, syp), (mx, my), (hx, hy)], 12)
    w = k.lw * .85 if w is None else w
    if kind in ("flipper", "wing"):
        radii = [r * 1.3, r * 1.15, r * .95, r * .55] if kind == "flipper" else [r * 1.45, r * 1.25, r * .9, r * .45]
        sh = k.tube(path, radii)
        k.part(sh, col, w)
        if kind == "wing":                                   # feather tips
            for j in (-1, 0, 1):
                p = path[-3 - j * 2] if 0 <= len(path) - 3 - j * 2 < len(path) else path[-3]
                q = path[-1]
                k.stroke([p, ((p[0] * .4 + q[0] * .6) + j * r * .3, (p[1] * .4 + q[1] * .6) + r * .25)], r * .28,
                         darken(col, .25), (.2, 1, .2))
        k.form(sh, .26, .4)
        return (hx, hy)
    sh = k.tube(path, [r * 1.05, r * .95, r * .9])
    k.part(sh, col, w)
    k.form(sh, .24, .35)
    hand(k, sx, hx, hy, r, hand_col or col, pose, path, w)
    return (hx, hy)


def hand(k, sx, hx, hy, r, col, pose, path, w):
    dx, dy = path[-1][0] - path[-3][0], path[-1][1] - path[-3][1]
    ln = math.hypot(dx, dy) or 1
    dx, dy = dx / ln, dy / ln
    cx_, cy_ = hx + dx * r * .5, hy + dy * r * .5
    hr = r * (1.45 if pose == "wave" else 1.3)
    if pose == "point":
        fx, fy = cx_ + sx * hr * .7, cy_ - hr * .25
        k.part(k.tube([(fx, fy), (fx + sx * hr * 1.4, fy - hr * .05)], [hr * .36, hr * .32]), col, w)
        k.part(k.E(cx_, cy_, hr, hr * .9), col, w, (.22, .3))
        return
    k.part(k.E(cx_, cy_, hr, hr * .95), col, w, (.22, .3))
    tx = cx_ - sx * hr * .78 if pose != "clap" else cx_ - sx * hr * .2
    k.part(k.rot_ell(tx, cy_ - hr * .35, hr * .42, hr * .28, -sx * 40), col, w * .8)
    if pose == "wave":                                     # finger gaps
        for j in (-1, 1):
            fx = cx_ + j * hr * .3
            k.stroke([(fx, cy_ - hr * .95), (fx, cy_ - hr * .45)], hr * .12, OUT, (.3, 1, .6))


def clap_marks(k, y, spread):
    for j, ang in enumerate((-55, -90, -125)):
        a = math.radians(ang)
        x0, y0 = math.cos(a) * spread, y + math.sin(a) * spread
        k.stroke([(x0, y0), (x0 + math.cos(a) * spread * .7, y0 + math.sin(a) * spread * .7)], spread * .28,
                 (255, 200, 70), (.6, 1, .3))


def two_arms(k, arms, shoulders, L, r, col, kind="paw", hand_col=None, clap_x=2.5, layer="all"):
    """Both arms for a pose. shoulders = (dx, y) of the right shoulder; left is mirrored.
    layer: 'low' draws only lowered arms (call before the head), 'high' only raised ones (call after the head,
    so a waving hand is never hidden behind it)."""
    dx, y = shoulders
    hands = []
    for sx in (-1, 1):
        pose = side_pose(arms, sx)
        if layer != "all" and (pose in ("wave", "up")) != (layer == "high"):
            continue
        hands.append(limb(k, sx, (sx * dx, y), L, r, col, pose, kind, hand_col, clap_x))
    if arms == "clap" and layer != "high" and len(hands) == 2:
        clap_marks(k, hands[0][1] - r * 1.4, r * 1.4)
    return hands


# ================================================================= the cast
def _penguin(d, W, H, c, mouth_, eyes, emo, arms):
    """Pip: a small round blue penguin chick. Silhouette = egg + fluffy curl tuft + flippers + big orange feet."""
    k = Toon(d, W, H)
    body, belly, acc = c["body"], c["belly"], c["accent"]
    dark = darken(body, .18)
    # fluffy chick tuft (behind the head)
    for path, r in (([(-1, 27), (-5, 16), (-1, 7)], 3.4), ([(2, 26), (3, 13), (9, 9)], 3.0), ([(5, 28), (11, 21), (15, 22)], 2.4)):
        sh = k.tube(_bez(path, 10), [r, r * .7, r * .2])
        k.part(sh, body, shade=(.2, .3))
    # feet
    for sx in (-1, 1):
        toes = [k.E(sx * 11 + dx, 95.6 - abs(dx) * .12, 5.2, 3.4) for dx in (-4.2, 0, 4.2)]
        k.group(toes, acc, shade=(.25, .35))
    # body
    bsh = k.egg(0, 60, 31, 36.5, top=.84)
    k.part(bsh, body)
    face = [k.E(sx * 10.2, 47, 12.6, 12.4) for sx in (-1, 1)] + [k.E(0, 55, 13, 8)]
    for sh in face:
        k.fill(sh, belly)
    k.fill(k.egg(0, 79, 20, 15.5, top=.9), belly)
    # tiny feather fluff marks on the belly
    for dx, dy in ((-7, 76), (0, 82), (7, 76)):
        k.stroke(_bez([(dx - 1.6, dy), (dx, dy + 1.3), (dx + 1.6, dy)], 6), 1.0, darken(belly, .12), (.2, 1, .2))
    k.form(bsh, .32, .5, .2)
    two_arms(k, arms, (27.5, 59), 15, 4.4, dark, "flipper", clap_x=6)
    for sx in (-1, 1):
        eye(k, sx * 10.2, 46, 8.6, sx, eyes, emo, iris=(46, 78, 150), brow_col=darken(body, .5))
    k.blush(-19, 56.5, 4.6, 3.0)
    k.blush(19, 56.5, 4.6, 3.0)
    # beak: upper bill + a lower bill that drops with the mouth level
    drop = [0, 2.6, 5.2][mouth_]
    by = 55.5
    if drop:
        k.part(k.E(0, by + drop * .45, 3.3, 1.2 + drop * .55), MOUTH_DARK, k.li)
        k.clip_paste(k.E(0, by + drop * .45, 3.3, 1.2 + drop * .55), k.E(0, by + drop * .9, 2.4, drop * .35), TONGUE)
        k.part(k.poly(_bez([(-3.6, by + drop), (0, by + drop + 3.4), (3.6, by + drop)], 8)), darken(acc, .08), k.li)
    up = _bez([(-4.6, by - .8), (0, by - 3.6), (4.6, by - .8)], 8) + _bez([(4.6, by - .8), (0, by + 4.4), (-4.6, by - .8)], 8)[1:]
    k.part(k.poly(up), acc, k.li * 1.2, (.22, .3))
    k.fill(k.E(-1.4, by - 1.6, 1.3, .6), lighten(acc, .55))
    if mouth_ == 0 and MOUTH[emo][0] < 0:
        k.stroke(_bez([(-3, by + 3.6), (0, by + 2.4), (3, by + 3.6)], 6), 1.0, OUT)


def _bunny(d, W, H, c, mouth_, eyes, emo, arms):
    """Mimi: pink bunny, one tall ear + one floppy ear, flower behind the ear, cotton tail, big feet."""
    k = Toon(d, W, H)
    body, belly, acc = c["body"], c["belly"], c["accent"]
    inner = (255, 128, 168)
    droop = emo in ("sad", "worried", "sleepy")
    perk = emo in ("excited", "surprised")
    # ears: (path, radii)
    tall = [(-7, 30), (-11, 14), (-9.5, 1.5)]
    flop = [(7, 30), (14, 13), (28, 18)] if not perk else [(7, 30), (12, 14), (11, 2)]
    if droop:
        tall = [(-7, 30), (-17, 18), (-29, 26)]
        flop = [(7, 30), (17, 18), (29, 26)]
    for path in (tall, flop):
        pts = _bez(path, 14)
        k.part(k.tube(pts, [3.6, 6.0, 5.6, 3.6]), body, shade=(.28, .4))
        k.fill(k.tube(pts[2:-1], [1.4, 3.2, 3.0, 1.6]), inner)
        k.form(k.tube(pts[2:-1], [1.4, 3.2, 3.0, 1.6]), .25, 0)
    # cotton tail
    k.part(k.scallop(14, 85, 5.2, 4.8, 8, .14), lighten(body, .55), shade=(.25, .3))
    # feet + body
    for sx in (-1, 1):
        k.part(k.egg(sx * 9.5, 95, 8.4, 4.4, top=1.05), body, shade=(.28, .35))
        k.fill(k.E(sx * 9.5, 95.6, 4.2, 2.2), lighten(inner, .45))
    bsh = k.egg(0, 79, 15.5, 15.5, top=.78)
    k.part(bsh, body)
    k.fill(k.egg(0, 82, 9.5, 10, top=.85), belly)
    k.form(bsh, .32, .45)
    head = k.egg(0, 46, 24.5, 20.5, top=.92, bot=1.04)
    k.occlude(bsh, head, 3.0)
    two_arms(k, arms, (11.5, 70), 12, 3.3, body, "paw", clap_x=3.2, layer="low")
    k.part(head, body)
    k.fill(k.E(-2.9, 54.5, 4.2, 3.2), belly)
    k.fill(k.E(2.9, 54.5, 4.2, 3.2), belly)
    k.form(head, .3, .5, .18)
    two_arms(k, arms, (11.5, 70), 13, 3.3, body, "paw", layer="high")
    # flower tucked at the base of the tall ear
    fx, fy = -15.5, 28
    for ang in (-30, 40):
        a = math.radians(ang + 180)
        k.part(k.rot_ell(fx + math.cos(a) * 5.4, fy + math.sin(a) * 5.4 + 1, 3.6, 1.6, ang), (110, 190, 90), k.li)
    for i in range(5):
        a = math.radians(i * 72 - 90)
        k.part(k.rot_ell(fx + math.cos(a) * 3.3, fy + math.sin(a) * 3.3, 3.1, 2.3, i * 72 - 90), acc, k.li, (.2, .3))
    k.part(k.E(fx, fy, 1.9, 1.9), (255, 150, 60), k.li)
    k.fill(k.E(fx - .6, fy - .6, .6, .6), (255, 230, 170))
    for sx in (-1, 1):
        eye(k, sx * 9, 44, 7.8, sx, eyes, emo, iris=(120, 60, 110), lash=True, brow_col=darken(body, .5))
    k.blush(-15.5, 52.5, 4.0, 2.6)
    k.blush(15.5, 52.5, 4.0, 2.6)
    nose(k, 0, 51.4, 2.0, (240, 100, 140))
    k.stroke([(0, 52.6), (0, 54.6)], .9, OUT, (1, 1, 1))
    mouth(k, 0, 56, 4.6, mouth_, emo, buck=True)


def _dino(d, W, H, c, mouth_, eyes, emo, arms):
    """Bo: big gentle green dinosaur. Pear body, bean head, soft yellow back plates, curling tail, belly plates."""
    k = Toon(d, W, H)
    body, belly, acc = c["body"], c["belly"], c["accent"]
    spot = darken(body, .14)
    # tail curling up on the right, with little plates
    tail = _bez([(14, 82), (34, 92), (46, 84), (47, 70)], 18)
    for t in (.45, .7, .88):
        i = int(t * (len(tail) - 1))
        (x0, y0), (x1, y1) = tail[i - 1], tail[i + 1]
        nx, ny = (y1 - y0), -(x1 - x0)
        ln = math.hypot(nx, ny) or 1
        nx, ny = nx / ln, ny / ln
        px, py = tail[i]
        rr = 6.5 * (1 - t * .55)
        k.part(k.poly(_bez([(px - (x1 - x0) * 1.4, py - (y1 - y0) * 1.4), (px + nx * rr * 1.6, py + ny * rr * 1.6),
                            (px + (x1 - x0) * 1.4, py + (y1 - y0) * 1.4)], 8)), acc, shade=(.25, .3))
    tsh = k.tube(tail, [9, 7, 4.2, 1.8])
    k.part(tsh, body, shade=(.3, .35))
    # back plates peeking behind head and shoulders
    for ang, rr, cxx, cyy, rx, ry in ((-70, 4.4, 0, 30, 24, 19), (-42, 5.2, 0, 30, 24, 19), (-14, 5.4, 0, 30, 24, 19),
                                      (-24, 5.4, 0, 70, 26, 25), (0, 5.0, 0, 70, 26, 25)):
        a = math.radians(ang)
        px, py = cxx + math.cos(a) * rx * .93, cyy + math.sin(a) * ry * .93
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -ny, nx
        tip = (px + nx * rr * 1.9, py + ny * rr * 1.9)
        pts = _bez([(px - tx * rr, py - ty * rr), (tip[0] - tx * rr * .9, tip[1] - ty * rr * .9), tip], 6) + \
            _bez([tip, (tip[0] + tx * rr * .9, tip[1] + ty * rr * .9), (px + tx * rr, py + ty * rr)], 6)[1:]
        k.part(k.poly(pts), acc, shade=(.25, .35))
    # legs
    for sx in (-1, 1):
        leg = k.egg(sx * 13, 90.5, 8.6, 8.5, top=.92)
        k.part(leg, body, shade=(.3, .35))
        for dx in (-3.6, 0, 3.6):
            k.part(k.E(sx * 13 + dx, 97, 1.9, 1.3), (255, 245, 215), k.li * .7)
    # body + belly plates
    bsh = k.egg(0, 70, 27, 24.5, top=.8)
    k.part(bsh, body)
    bel = k.egg(0, 75, 17, 17.5, top=.85)
    k.fill(bel, belly)
    for yy in (66, 72, 78, 84):
        hw = 17 * math.sqrt(max(0, 1 - ((yy - 75) / 17.5) ** 2)) * .82
        k.stroke(_bez([(-hw, yy - 1), (0, yy + 1.4), (hw, yy - 1)], 10), 1.0, darken(belly, .16), (.3, 1, .3))
    for dx, dy, r in ((-21, 62, 2.4), (-19, 70, 1.6), (21, 66, 2.0)):
        k.fill(k.E(dx, dy, r, r * .85), spot)
    k.form(bsh, .32, .45)
    head = k.egg(0, 30, 25, 20, top=.82, bot=1.06)
    k.occlude(bsh, head, 3.5)
    two_arms(k, arms, (21, 61), 11, 4.3, body, "paw", clap_x=4.2, layer="low")
    k.part(head, body)
    k.fill(k.egg(0, 40.5, 16.5, 8.5, top=1.0, bot=.9), belly)
    for dx, dy, r in ((-14, 16, 2.0), (-17.5, 21, 1.3), (15, 17, 1.6)):
        k.fill(k.E(dx, dy, r, r * .85), spot)
    k.form(head, .3, .5, .18)
    two_arms(k, arms, (21, 61), 12, 4.3, body, "paw", layer="high")
    for sx in (-1, 1):
        k.fill(k.E(sx * 3.4, 33.2, 1.1, .75), darken(body, .45))
    for sx in (-1, 1):
        eye(k, sx * 9.5, 23.5, 7.6, sx, eyes, emo, iris=(110, 70, 40), brow_col=darken(body, .5))
    k.blush(-17.5, 34, 4.2, 2.8)
    k.blush(17.5, 34, 4.2, 2.8)
    mouth(k, 0, 39.5, 7.2, mouth_, emo, teeth=True)


def _fox(d, W, H, c, mouth_, eyes, emo, arms):
    """Zuzu: orange fox explorer. Big dark-tipped ears, cheek ruff, bandana, backpack + straps, white-tipped tail."""
    k = Toon(d, W, H)
    body, belly, acc = c["body"], c["belly"], c["accent"]
    sock = (120, 70, 60)
    # big bushy tail sweeping up on the right
    tail = _bez([(9, 88), (30, 92), (40, 70), (31, 50)], 18)
    radii = [3.5, 7.5, 9.0, 7.6, 1.5]
    k.part(k.tube(tail, radii), body, shade=(.3, .35))
    tip = tail[12:]
    k.part(k.tube(tip, [7.4, 6.4, 3.8, 1.5]), belly, k.li)
    k.form(k.tube(tip, [7.4, 6.4, 3.8, 1.5]), .25, 0)
    # backpack peeking out on both sides + bedroll on top
    pack = k.blob(0, 72, 19.5, 13, [(0, 30, .02)])
    k.part(pack, acc, shade=(.3, .3))
    k.part(k.tube([(-14, 59.5), (14, 59.5)], [3.2, 3.2]), (255, 205, 90), shade=(.25, .3))
    for sx in (-1, 1):
        k.stroke([(sx * 14, 57), (sx * 14, 62)], .9, darken((255, 205, 90), .3), (1, 1, 1))
    # legs + socks
    for sx in (-1, 1):
        k.part(k.egg(sx * 7.5, 90, 5.4, 6.4, top=.95), body)
        k.part(k.egg(sx * 8, 95.2, 7.4, 4.1, top=1.05), sock, shade=(.25, .35))
    bsh = k.egg(0, 77, 14.5, 15, top=.78)
    k.part(bsh, body)
    k.fill(k.egg(0, 81, 8.5, 10, top=.8), belly)
    # backpack straps + chest strap + buckle
    for sx in (-1, 1):
        k.part(k.tube(_bez([(sx * 9.5, 63), (sx * 8.5, 72), (sx * 9.5, 84)], 8), [1.7, 1.7]), acc, k.li)
    k.part(k.tube([(-8.6, 73), (8.6, 73)], [1.1, 1.1]), darken(acc, .15), k.li)
    k.part(k.E(0, 73, 2.0, 1.6), (255, 205, 90), k.li * .8)
    k.form(bsh, .3, .4)
    # ears
    for sx in (-1, 1):
        base_in, base_out, tipp = (sx * 6, 31), (sx * 21, 36), (sx * 20, 5.5)
        ear = _bez([base_in, (sx * 10, 14), tipp], 10) + _bez([tipp, (sx * 25, 20), base_out], 10)[1:]
        k.part(k.poly(ear), body, shade=(.28, .4))
        k.fill(k.poly(_bez([(sx * 9.5, 31), (sx * 12, 19), (sx * 19.4, 11)], 8) + _bez([(sx * 19.4, 11), (sx * 21, 22), (sx * 18.5, 33)], 8)[1:]),
               (255, 225, 205))
        tipsh = k.poly(_bez([(sx * 15.4, 15), (sx * 17, 10), tipp], 6) + _bez([tipp, (sx * 22.6, 12), (sx * 22.6, 18.5)], 6)[1:] + [(sx * 19, 17)])
        k.part(tipsh, (95, 60, 70), k.li * .8)
    head = k.blob(0, 42, 22.5, 18.5, [(155, 22, .2), (25, 22, .2), (140, 10, .08), (40, 10, .08)])
    k.occlude(bsh, head, 3.5)
    two_arms(k, arms, (12, 67), 12, 3.2, body, "paw", hand_col=sock, clap_x=3.0, layer="low")
    # bandana knot under the chin
    k.part(k.poly(_bez([(-10, 58), (0, 66), (10, 58)], 10) + [(0, 60.5)]), (255, 205, 90), k.li, (.25, .3))
    k.part(head, body)
    for sx in (-1, 1):
        k.fill(k.blob(sx * 7.5, 50.5, 9.6, 7.0, [(90 + sx * 60, 30, .15)]), belly)
    k.fill(k.E(0, 53, 7.5, 6.5), belly)
    k.form(head, .3, .5, .18)
    two_arms(k, arms, (12, 67), 13, 3.2, body, "paw", hand_col=sock, layer="high")
    for sx in (-1, 1):
        eye(k, sx * 8.6, 40, 7.4, sx, eyes, emo, iris=(140, 85, 30), lash=True, brow_col=darken(body, .45))
    k.blush(-15, 50, 3.6, 2.4)
    k.blush(15, 50, 3.6, 2.4)
    nose(k, 0, 48.6, 2.5)
    k.stroke([(0, 50), (0, 52.4)], .9, OUT, (1, 1, 1))
    mouth(k, 0, 54, 5.0, mouth_, emo)


def _owl(d, W, H, c, mouth_, eyes, emo, arms):
    """Nana Owl: round purple owl. Feather ear tufts, heart face disc, round gold glasses with glint, scalloped chest."""
    k = Toon(d, W, H)
    body, belly, acc = c["body"], c["belly"], c["accent"]
    dark = darken(body, .2)
    for sx in (-1, 1):        # ear tufts
        for j, (dx, dy, r) in enumerate(((0, 0, 4.4), (4.5, 3.5, 3.2))):
            p = _bez([(sx * (11 + dx), 31 + dy), (sx * (17 + dx), 22 + dy), (sx * (23 + dx * .4), 15 + dy * 1.2)], 10)
            k.part(k.tube(p, [r * .8, r, r * .75, r * .15]), body if j == 0 else dark, shade=(.2, .3))
    for sx in (-1, 1):        # feet
        k.group([k.E(sx * 8 + dx, 96, 2.6, 2.6) for dx in (-3, 0, 3)], acc, shade=(.25, .3))
    bsh = k.egg(0, 59, 29, 37, top=.8)
    k.part(bsh, body)
    k.fill(k.egg(0, 76, 18.5, 18.5, top=.85), belly)
    for row in range(4):      # scalloped chest feathers
        yy = 66 + row * 5.2
        hw = 18 * math.sqrt(max(0, 1 - ((yy - 76) / 18.5) ** 2)) * .75
        n = max(2, int(hw / 3.5))
        for j in range(n):
            xx = -hw + (j + .5 + (row % 2) * .5) * (2 * hw / (n + .5))
            k.stroke(_bez([(xx - 2, yy), (xx, yy + 2.2), (xx + 2, yy)], 6), .9, darken(belly, .14), (.2, 1, .2))
    for dx, dy in ((-6, 28), (0, 26.5), (6, 28)):       # forehead feather marks
        k.stroke(_bez([(dx - 1.6, dy), (dx, dy + 1.4), (dx + 1.6, dy)], 6), .9, dark, (.2, 1, .2))
    k.form(bsh, .32, .5, .2)
    two_arms(k, arms, (25, 60), 15, 5.2, dark, "wing", clap_x=7)
    # heart-shaped face disc
    for sx in (-1, 1):
        k.fill(k.E(sx * 9.8, 43, 12.2, 11.6), lighten(belly, .35))
    k.form(k.E(0, 43, 22, 11.6), .14, 0, .1)
    for sx in (-1, 1):
        eye(k, sx * 9.8, 43, 7.4, sx, eyes, emo, iris=(150, 95, 40), lash=True, brow=False)
    # glasses
    rim = (226, 168, 66)
    for sx in (-1, 1):
        ex, ey = k.P(sx * 9.8, 43)
        R, t = 10.0 * k.u, 1.5 * k.u
        lens = ("e", ex, ey, R - t / 2, R - t / 2)
        k.glaze(lens, (235, 240, 255), .18)
        glint = k.poly([(sx * 9.8 - 6, 43 - 1.5), (sx * 9.8 - 2.5, 43 - 7.5), (sx * 9.8 - .5, 43 - 7), (sx * 9.8 - 4, 43 - 1)])
        k.clip_paste(lens, glint, (255, 255, 255), .7)
        k.clip_paste(lens, k.poly([(sx * 9.8 + 3.5, 43 + 6), (sx * 9.8 + 6.8, 43 + 1), (sx * 9.8 + 7.6, 43 + 1.6), (sx * 9.8 + 4.4, 43 + 6.6)]),
                     (255, 255, 255), .55)
        d.ellipse([ex - R - k.li, ey - R - k.li, ex + R + k.li, ey + R + k.li], outline=OUT, width=int(t + 2 * k.li))
        d.ellipse([ex - R, ey - R, ex + R, ey + R], outline=rim, width=int(t))
        d.arc([ex - R + t * .4, ey - R + t * .4, ex + R - t * .4, ey + R - t * .4], 200, 250, fill=lighten(rim, .6), width=max(1, int(t * .3)))
    k.stroke(_bez([(-1.2, 41.5), (0, 40), (1.2, 41.5)], 6), 2.2, OUT, (1, 1, 1))
    k.stroke(_bez([(-1.0, 41.3), (0, 40.1), (1.0, 41.3)], 6), 1.0, rim, (1, 1, 1))
    for sx in (-1, 1):        # feathery brows above the glasses
        _brow(k, sx * 9.8, 43 - 3.0, 7.4, sx, emo, darken(body, .45))
    k.blush(-17, 53, 3.6, 2.4)
    k.blush(17, 53, 3.6, 2.4)
    drop = [0, 2.2, 4.4][mouth_]
    by = 53
    if drop:
        k.part(k.E(0, by + 1.6 + drop * .4, 2.6, 1.0 + drop * .5), MOUTH_DARK, k.li)
        k.part(k.poly(_bez([(-2.6, by + 1.8 + drop), (0, by + 4.2 + drop), (2.6, by + 1.8 + drop)], 6)), darken(acc, .1), k.li)
    beak = _bez([(-3.4, by - 1.2), (0, by - 3.0), (3.4, by - 1.2)], 6) + _bez([(3.4, by - 1.2), (.8, by + 3.4), (0, by + 4.6)], 6)[1:] + \
        _bez([(0, by + 4.6), (-.8, by + 3.4), (-3.4, by - 1.2)], 6)[1:]
    k.part(k.poly(beak), acc, k.li * 1.1, (.22, .3))
    if mouth_ == 0 and MOUTH[emo][0] > .3:
        for sx in (-1, 1):
            k.stroke(_bez([(sx * 3.2, by + .6), (sx * 4.6, by + 1.4), (sx * 5.6, by + .2)], 6), .9, OUT, (.3, 1, .3))


def _frog(d, W, H, c, mouth_, eyes, emo, arms):
    """Hoppy: the star. A bright aqua tree frog: eye domes on top of a wide head, crouched springy legs with round
    toe pads, a speckled back and an orange hero scarf. Silhouette = wide head + two domes + bent knees."""
    k = Toon(d, W, H)
    body, belly, acc = c["body"], c["belly"], c["accent"]
    spot = darken(body, .16)
    pad = lighten(acc, .25)
    crouch = 2.0 if emo in ("excited", "surprised") else (-1.5 if emo in ("sad", "sleepy", "worried") else 0)
    # back legs: folded haunches with long feet and round toe pads
    for sx in (-1, 1):
        k.part(k.egg(sx * 21, 84 - crouch, 12.5, 10.5, top=.9), body, shade=(.3, .35))
        k.stroke(_bez([(sx * 15, 80 - crouch), (sx * 22, 77 - crouch), (sx * 28, 82 - crouch)], 8), 1.0, spot, (.2, 1, .2))
        k.part(k.egg(sx * 23, 95, 11, 3.6, top=1.05), body, shade=(.25, .3))
        for dx in (-7, -1.5, 4.5):
            tx = sx * 23 + sx * dx
            k.part(k.E(tx, 96.4, 2.3, 1.9), pad, k.li * .8, (.2, .25))
    # body + speckled belly
    bsh = k.egg(0, 71 - crouch * .5, 23, 21.5, top=.82)
    k.part(bsh, body)
    k.fill(k.egg(0, 76 - crouch * .5, 15, 14.5, top=.86), belly)
    for dx, dy, r in ((-6, 72, 1.0), (4, 78, 1.2), (-2, 84, .9), (8, 71, .8)):
        k.fill(k.E(dx, dy - crouch * .5, r, r * .85), darken(belly, .1))
    for dx, dy, r in ((-19, 64, 2.2), (19, 67, 1.8), (-16, 74, 1.3)):
        k.fill(k.E(dx, dy - crouch * .5, r, r * .8), spot)
    k.form(bsh, .32, .45)
    # head: wide and flat, with two eye domes on top
    hy = 42 - crouch * .6
    head = k.egg(0, hy, 30, 17.5, top=1.02, bot=.95)
    domes = [k.E(sx * 13.5, hy - 15, 10.2, 9.6) for sx in (-1, 1)]
    k.occlude(bsh, head, 3.2)
    two_arms(k, arms, (17.5, 61 - crouch * .5), 12, 3.8, body, "paw", clap_x=3.6, layer="low")
    for dm in domes:
        k.part(dm, body)
    k.part(head, body)
    for dm in domes:
        k.form(dm, .25, .55, .15)
    k.fill(k.egg(0, hy + 9.5, 21, 6.2, top=1.0, bot=.85), belly)            # pale chin
    for dx, dy, r in ((-21, hy - 3, 2.0), (-24.5, hy + 2, 1.3), (22, hy - 2, 1.7)):
        k.fill(k.E(dx, dy, r, r * .85), spot)
    k.form(head, .3, .5, .16)
    # orange hero scarf: a band at the neck, knot and two tails on the right
    sy = hy + 16
    band = k.tube(_bez([(-19, sy - 1.5), (0, sy + 3.2), (19, sy - 1.5)], 14), [3.0, 3.6, 3.0])
    k.part(band, acc, shade=(.28, .35))
    k.stroke(_bez([(-14, sy + .3), (0, sy + 3.6), (14, sy + .3)], 12), .9, darken(acc, .22), (.2, 1, .2))
    for path in ([(13, sy + 1.5), (19, sy + 8), (17.5, sy + 14)], [(13, sy + 1.5), (22.5, sy + 5), (26, sy + 10.5)]):
        k.part(k.tube(_bez(path, 10), [2.6, 2.4, 1.6]), acc, shade=(.28, .35))
    k.part(k.E(13, sy + 1.5, 3.4, 2.9), darken(acc, .06), shade=(.25, .3))
    two_arms(k, arms, (17.5, 61 - crouch * .5), 12, 3.8, body, "paw", layer="high")
    for sx in (-1, 1):
        eye(k, sx * 13.5, hy - 14.5, 7.4, sx, eyes, emo, iris=(196, 120, 30), brow_col=darken(body, .5))
    for sx in (-1, 1):
        k.fill(k.E(sx * 3.2, hy + .5, .9, .65), darken(body, .45))              # nostrils
    k.blush(-20.5, hy + 5, 4.4, 2.8)
    k.blush(20.5, hy + 5, 4.4, 2.8)
    if mouth_ == 0 and emo in ("happy", "proud", "calm", "excited"):            # the frog's long, wide grin
        k.stroke(_bez([(-14.5, hy + 2.6), (0, hy + 10.5), (14.5, hy + 2.6)], 16), 1.9, OUT, (.3, 1, .3))
        for sx in (-1, 1):                                                      # dimples at the grin's corners
            k.stroke(_bez([(sx * 14.2, hy + 1.4), (sx * 15.6, hy + 2.8), (sx * 14.8, hy + 4.4)], 6), 1.0, OUT, (.3, 1, .3))
    else:
        mouth(k, 0, hy + 6.5, 7.6, mouth_, emo)


def _sun(d, W, H, c, mouth_, eyes, emo, arms):
    """Sunny: a round sun face inside a ring of soft flame-shaped rays. Rays shift with mouth and emotion,
    so when Sunny talks the rays wiggle."""
    k = Toon(d, W, H)
    body, acc = c["body"], c["accent"]
    cy = 50
    phase = mouth_ * 4.5 + EMOTIONS.index(emo) * 2.0 if emo in EMOTIONS else 0
    boost = {"excited": 1.12, "surprised": 1.08, "proud": 1.06, "sad": .92, "sleepy": .9, "worried": .95}.get(emo, 1.0)
    for layer in (0, 1):
        n = 12
        for i in range(n):
            a0 = math.radians(i * 360 / n + phase + (15 if layer else 0))
            if layer == 0:
                r0, r1, wd, col = 30, (47 if i % 2 else 42) * boost, .2, acc
            else:
                r0, r1, wd, col = 30, 38 * boost, .14, _mix(body, acc, .35)
            curl = .2
            tip = (math.cos(a0 + curl * .5) * r1, cy + math.sin(a0 + curl * .5) * r1)
            l0 = (math.cos(a0 - wd) * r0, cy + math.sin(a0 - wd) * r0)
            r0p = (math.cos(a0 + wd) * r0, cy + math.sin(a0 + wd) * r0)
            mid = (r0 + r1) * .55
            c1 = (math.cos(a0 - wd * .7) * mid, cy + math.sin(a0 - wd * .7) * mid)
            c2 = (math.cos(a0 + wd * 1.4) * mid, cy + math.sin(a0 + wd * 1.4) * mid)
            pts = _bez([l0, c1, tip], 8) + _bez([tip, c2, r0p], 8)[1:]
            k.part(k.poly(pts), col, k.lw * .85, (.22, .35))
    face = k.E(0, cy, 33, 33)
    k.part(face, body)
    for j, (dx, dy, r, kk) in enumerate(((-3, -3, 28, .18), (-6, -6, 20, .32), (-9, -9, 10, .5))):
        k.glaze(k.E(dx, cy + dy, r, r), (255, 250, 210), kk * .5)
    k.form(face, .22, .5, .14, col=body)
    for sx in (-1, 1):
        eye(k, sx * 11, cy - 4, 8.2, sx, eyes, emo, iris=(150, 80, 20), lash=True, brow_col=darken(acc, .35))
    k.blush(-20.5, cy + 7, 5.0, 3.2, c.get("cheek", BLUSH), .6)
    k.blush(20.5, cy + 7, 5.0, 3.2, c.get("cheek", BLUSH), .6)
    mouth(k, 0, cy + 10.5, 8.0, mouth_, emo, teeth=True)


DRAW = {"frog": _frog, "penguin": _penguin, "bunny": _bunny, "dinosaur": _dino, "fox": _fox, "owl": _owl, "sun": _sun}
ASPECT = {"frog": 1.02, "penguin": .82, "bunny": .82, "dinosaur": 1.05, "fox": .95, "owl": .9, "sun": 1.0}
SCALE = {"hoppy": .9, "pip": .82, "mimi": .95, "bo": 1.12, "zuzu": .95, "nana": .95, "sunny": 1.0}   # size differences = personality


# story characters designed per episode (id -> design spec); filled by register_guests()
GUESTS: dict[str, dict] = {}


def register_guests(script: dict) -> None:
    import json as _json
    for g in script.get("characters") or []:
        if g.get("id") and g["id"] not in CAST:
            GUESTS[g["id"]] = g
            GUESTS[g["id"]]["_json"] = _json.dumps({k: v for k, v in g.items() if not k.startswith("_")}, sort_keys=True)


def shade(img: Image.Image) -> Image.Image:
    """Final soft light pass over a finished sprite: a gentle top-left key light that unifies the separately
    lit forms. Applied once per cached pose."""
    w, h = img.size
    if w < 8 or h < 8 or img.mode != "RGBA":
        return img
    return ImageChops.multiply(img, _keylight(w, h))


@lru_cache(maxsize=48)
def _keylight(w: int, h: int) -> Image.Image:
    grad = Image.linear_gradient("L").rotate(-35, resample=Image.BILINEAR, expand=False).resize((w, h))
    light = grad.point(lambda v: int(255 - v * .08))
    return Image.merge("RGBA", (light, light, light, Image.new("L", (w, h), 255)))


def _halo(img: Image.Image) -> Image.Image:
    """Sunny's soft glow, added at final size (cheap)."""
    w, h = img.size
    s = 8
    small = Image.new("L", (max(1, w // s), max(1, h // s)), 0)
    r = w * .31 / s
    ImageDraw.Draw(small).ellipse([w / s / 2 - r, h / s / 2 - r, w / s / 2 + r, h / s / 2 + r], fill=120)
    small = small.filter(ImageFilter.GaussianBlur(max(1, r * .3))).resize((w, h), Image.BILINEAR)
    glow = Image.new("RGBA", (w, h), (255, 236, 150, 0))
    glow.putalpha(small)
    glow.alpha_composite(img)
    return glow


def supersample(height: float) -> int:
    """Big sprites need fewer sub-samples for the same smoothness; keeps 700px poses fast."""
    return SS if height < 480 else 2


def _finish(im: Image.Image, ss: int = SS) -> Image.Image:
    """Box-filter the supersampled drawing down: clean anti-aliasing at a fraction of LANCZOS' cost."""
    return im.reduce(ss) if im.width >= ss and im.height >= ss else im


def sprite(char_id: str, height: int, mouth: int = 0, eyes: str = "open", emotion: str = "happy",
           arms: str = "down") -> Image.Image:
    from .styles import CURRENT
    style = CURRENT["style"]
    guest = char_id not in CAST and char_id in GUESTS
    key = GUESTS[char_id]["_json"] if guest else char_id   # story characters: cached by full design, not id
    if style == "classic":
        return _base_sprite(key, char_id, guest, height, mouth, eyes, emotion, arms)
    return _styled_sprite(key, char_id, guest, height, mouth, eyes, emotion, arms, style)


def _base_sprite(key, char_id, guest, height, mouth, eyes, emotion, arms):
    if guest:
        from .designer import sprite_from_json
        return sprite_from_json(key, height, mouth, eyes, emotion, arms)
    return _cast_sprite(char_id, height, mouth, eyes, emotion, arms)


@lru_cache(maxsize=160)
def _styled_sprite(key, char_id, guest, height, mouth, eyes, emotion, arms, style):
    from .styles import sprite_fx
    return sprite_fx(_base_sprite(key, char_id, guest, height, mouth, eyes, emotion, arms), style)


@lru_cache(maxsize=180)
def _cast_sprite(char_id: str, height: int, mouth: int = 0, eyes: str = "open", emotion: str = "happy",
                 arms: str = "down") -> Image.Image:
    c = CAST.get(char_id) or CAST["pip"]
    sp = c["species"]
    ss = supersample(height)
    H = int(height) * ss
    W = int(int(height * ASPECT.get(sp, .9)) * ss)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    DRAW[sp](ImageDraw.Draw(im), W, H, c["colors"], max(0, min(2, int(mouth))), "closed" if eyes == "closed" else "open",
             emotion if emotion in EMOTIONS else "happy", arms if arms in ARMS else "down")
    out = _finish(im, ss)
    return _halo(out) if sp == "sun" else shade(out)


def shadow(width: int) -> Image.Image:
    return _shadow(int(width))


@lru_cache(maxsize=32)
def _shadow(width: int) -> Image.Image:
    im, d = canvas(width, max(4, width // 5))
    d.ellipse([0, 0, width * SS - 1, width // 5 * SS - 1], fill=(30, 20, 50, 60))
    return _finish(im)
