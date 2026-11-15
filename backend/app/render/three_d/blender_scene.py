"""Runs INSIDE Blender (bpy): builds the 3D sets + cast and renders the frames of a CartoonForge job.

    blender -b --factory-startup --python blender_scene.py -- job.json

job.json (written by three_d/__init__.py):
  W, H, fps, out_dir, first, last, samples, engine ("auto"|"cycles"|"eevee"), outline (bool)
  cast:   {id: {"kind": "cast"|"animal"|"human", "species", "colors": {...rgb lists}, ...design spec}}
  sets:   {set_id: SETS spec from render/sets.py (colours as lists)}
  frames: [state, ...] one per frame, see three_d/__init__.py frame_state()

World units: the wide shot sees 16 x 9 units at y=0; the ground is z=0 and sits 7% above the bottom of the
picture (like the 2D stage). Characters face -Y (the camera). Built from smooth primitives with soft "vinyl toy"
materials (subsurface + clear coat) and an inverted-hull cartoon outline.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Euler, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
JOB = json.load(open(ARGS[0]))
W, H = JOB["W"], JOB["H"]
VIEW_W, VIEW_H = 16.0, 9.0
GROUND_FRAC = .07
FOCAL = 35.0
SENSOR = 36.0
DIST = (VIEW_W / 2) / math.tan(math.atan(SENSOR / 2 / FOCAL))          # camera distance for the wide shot
OUTLINE = JOB.get("outline", True)
INK = (0.09, 0.06, 0.14)


def srgb(c):
    """0-255 sRGB list -> linear 0-1 tuple (Blender colours are linear)."""
    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
    return (ch(c[0]), ch(c[1]), ch(c[2]), 1.0)


def mix(a, b, k):
    return [a[i] * (1 - k) + b[i] * k for i in range(3)]


def lighten(c, k):
    return mix(c, [255, 255, 255], k)


def darken(c, k):
    return mix(c, [0, 0, 0], k)


# ================================================================= scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene
SC.render.resolution_x, SC.render.resolution_y = W, H
SC.render.resolution_percentage = 100
SC.render.fps = JOB["fps"]
SC.render.image_settings.file_format = "PNG"
SC.render.image_settings.color_mode = "RGB"
SC.render.use_lock_interface = True
SC.view_settings.view_transform = "Standard"           # punchy cartoon colours (AgX would desaturate them)
SC.view_settings.look = "None"
SC.view_settings.exposure = -0.15
SC.view_settings.gamma = 1.0


def setup_engine():
    want = JOB.get("engine", "auto")
    gpu = False
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type != "CPU"]
                if devs:
                    for d in prefs.devices:
                        d.use = d.type != "CPU"
                    gpu = True
                    break
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    if want == "eevee" or (want == "auto" and gpu and JOB.get("prefer_eevee_on_gpu")):
        SC.render.engine = "BLENDER_EEVEE_NEXT"
        SC.eevee.taa_render_samples = int(JOB.get("samples", 16)) * 2
        return "eevee"
    SC.render.engine = "CYCLES"
    SC.cycles.device = "GPU" if gpu else "CPU"
    SC.cycles.samples = int(JOB.get("samples", 16))
    SC.cycles.use_adaptive_sampling = True
    SC.cycles.adaptive_threshold = .05
    SC.cycles.use_denoising = True
    try:
        SC.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:  # noqa: BLE001
        pass
    SC.cycles.max_bounces = 4
    SC.cycles.diffuse_bounces = 2
    SC.cycles.glossy_bounces = 1
    SC.cycles.transmission_bounces = 2
    SC.cycles.transparent_max_bounces = 8
    SC.cycles.caustics_reflective = SC.cycles.caustics_refractive = False
    SC.render.use_persistent_data = True                 # keep the BVH between frames (big speed-up)
    return "cycles-gpu" if gpu else "cycles-cpu"


ENGINE = setup_engine()

# ================================================================= meshes (shared data, scaled per object)
_MESH = {}


def _mesh(kind):
    if kind in _MESH:
        return _MESH[kind]
    me = bpy.data.meshes.new(kind)
    bm = bmesh.new()
    if kind == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=22, radius=1.0)
    elif kind == "sphere_lo":
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=1.0)
    elif kind == "cone":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=28, radius1=1.0, radius2=0.0, depth=1.0)
    elif kind == "cyl":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=28, radius1=1.0, radius2=1.0, depth=1.0)
    elif kind == "cube":
        bmesh.ops.create_cube(bm, size=2.0)
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=.25, segments=3, affect="EDGES")
    elif kind == "torus":
        R, r, nu, nv = 1.0, .22, 40, 14
        verts = []
        for i in range(nu):
            a = 2 * math.pi * i / nu
            ring = []
            for j in range(nv):
                b = 2 * math.pi * j / nv
                ring.append(bm.verts.new(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b))))
            verts.append(ring)
        for i in range(nu):
            for j in range(nv):
                bm.faces.new((verts[i][j], verts[(i + 1) % nu][j], verts[(i + 1) % nu][(j + 1) % nv], verts[i][(j + 1) % nv]))
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [kind not in ("cube",)] * len(me.polygons))
    me.materials.append(None)
    me.materials.append(None)
    me.update()
    _MESH[kind] = me
    return me


# ================================================================= materials
_MAT = {}


def mat(name, rgb, rough=.45, sss=.12, coat=.25, emit=0.0, sheen=0.0, alpha=1.0):
    key = (name, tuple(round(v, 1) for v in rgb), rough, sss, coat, emit, sheen, alpha)
    if key in _MAT:
        return _MAT[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    col = srgb(rgb)
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = rough
    for k, v in (("Subsurface Weight", sss), ("Coat Weight", coat), ("Sheen Weight", sheen)):
        if k in b.inputs:
            b.inputs[k].default_value = v
    if "Subsurface Radius" in b.inputs:
        b.inputs["Subsurface Radius"].default_value = (.12, .08, .06)
    if emit:
        b.inputs["Emission Color"].default_value = col
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    _MAT[key] = m
    return m


def outline_mat():
    if "outline" in _MAT:
        return _MAT["outline"]
    m = bpy.data.materials.new("outline")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*INK, 1)
    mx = nt.nodes.new("ShaderNodeMixShader")
    lp = nt.nodes.new("ShaderNodeLightPath")
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(lp.outputs["Is Camera Ray"], inv.inputs[1])
    mxm = nt.nodes.new("ShaderNodeMath")
    mxm.operation = "MAXIMUM"
    nt.links.new(geo.outputs["Backfacing"], mxm.inputs[0])
    nt.links.new(inv.outputs["Value"], mxm.inputs[1])
    # transparent for back faces AND for every non-camera ray: the ink shell never casts shadows or bounces light
    nt.links.new(mxm.outputs["Value"], mx.inputs["Fac"])
    # flipped hull: its near side faces away from the camera (backfacing) -> transparent; only the rim that peeks
    # out around the silhouette faces the camera -> ink
    nt.links.new(em.outputs["Emission"], mx.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    m.use_backface_culling = True
    _MAT["outline"] = m
    return m


# ================================================================= object helpers
def empty(name, parent=None, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.parent = parent
    o.location = loc
    return o


def prim(name, kind, m, parent=None, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), outline=True, shadow=True):
    o = bpy.data.objects.new(name, _mesh(kind))
    bpy.context.collection.objects.link(o)
    o.parent = parent
    o.location = loc
    o.scale = scale
    o.rotation_euler = Euler(rot)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = m
    o.material_slots[1].link = "OBJECT"
    o.material_slots[1].material = outline_mat()
    if outline and OUTLINE:
        md = o.modifiers.new("ink", "SOLIDIFY")
        s = max(1e-3, (abs(scale[0]) + abs(scale[1]) + abs(scale[2])) / 3)
        md.thickness = .018 / s
        md.offset = 1.0
        md.use_flip_normals = True
        md.use_rim = False
        md.material_offset = 1
    if not shadow:
        o.visible_shadow = False
    return o


def arc_curve(name, parent, w, depth, m, loc=(0, 0, 0)):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = depth
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(2)
    for i, p in enumerate(sp.bezier_points):
        p.co = ((i - 1) * w, 0, 0)
        p.handle_left_type = p.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.parent = parent
    o.location = loc
    o.data.materials.append(m)
    o.visible_shadow = False
    return o


def set_arc(o, w, curve):
    """curve > 0 smile (corners up), < 0 frown."""
    pts = o.data.splines[0].bezier_points
    pts[0].co = (-w, 0, curve * w * .55)
    pts[1].co = (0, 0, -curve * w * .35)
    pts[2].co = (w, 0, curve * w * .55)


# ================================================================= faces (shared by everyone)
EMO = {                    # eye openness, brow raise, brow tilt (inner up +), smile curve, look (x, z)
    "happy": (1.0, .05, 0.0, .8, (0, 0)),
    "excited": (1.12, .22, -.1, 1.0, (0, .05)),
    "surprised": (1.22, .32, .05, 0.0, (0, .05)),
    "thinking": (1.0, .12, 0.0, .25, (.35, .35)),
    "sad": (.86, .06, .45, -.7, (0, -.25)),
    "worried": (1.0, .14, .35, -.3, (0, 0)),
    "proud": (.32, .1, -.05, .9, (0, 0)),
    "sleepy": (.5, -.04, .1, .3, (0, -.25)),
    "calm": (.82, .02, .05, .55, (0, 0)),
}


class Face:
    def __init__(self, name, head, eyes, eye_r, mouth_at, mouth_w, skin, iris=(80, 52, 40), brow_col=None,
                 beak=None, lashes=False, teeth=False):
        self.eyes, self.brows = [], []
        white = mat("eye_white", [250, 250, 252], rough=.15, sss=0, coat=.6)
        irm = mat(f"iris_{iris}", iris, rough=.2, sss=0, coat=.8)
        pup = mat("pupil", [20, 14, 26], rough=.15, sss=0, coat=.9)
        hi = mat("eye_hi", [255, 255, 255], emit=3.0, sss=0, coat=0)
        bc = mat(f"brow_{name}", brow_col or darken(skin, .55), rough=.6, sss=0, coat=0)
        for i, (ex, ey, ez) in enumerate(eyes):
            g = empty(f"{name}_eye{i}", head, (ex, ey, ez))
            prim(f"{name}_ew{i}", "sphere", white, g, scale=(eye_r * .86, eye_r * .6, eye_r), outline=True, shadow=False)
            look = empty(f"{name}_look{i}", g, (0, 0, 0))
            prim(f"{name}_ir{i}", "sphere", irm, look, loc=(0, -eye_r * .44, -eye_r * .05),
                 scale=(eye_r * .58, eye_r * .2, eye_r * .66), outline=False, shadow=False)
            prim(f"{name}_pu{i}", "sphere", pup, look, loc=(0, -eye_r * .56, -eye_r * .05),
                 scale=(eye_r * .32, eye_r * .12, eye_r * .38), outline=False, shadow=False)
            prim(f"{name}_hi{i}", "sphere_lo", hi, look, loc=(eye_r * .2 * (1 if i else 1), -eye_r * .64, eye_r * .2),
                 scale=(eye_r * .14, eye_r * .06, eye_r * .14), outline=False, shadow=False)
            lid = arc_curve(f"{name}_lid{i}", head, eye_r * .62, eye_r * .1, mat("lidink", INK, rough=.5, sss=0, coat=0),
                            (ex, ey - eye_r * .62, ez))
            lid.hide_render = True
            self.lids = getattr(self, "lids", []) + [lid]
            br = arc_curve(f"{name}_brow{i}", head, eye_r * .55, eye_r * .13, bc, (ex, ey - eye_r * .25, ez + eye_r * 1.25))
            set_arc(br, eye_r * .55, -.35)                      # an arch (middle up), never a V
            self.eyes.append((g, look, ez))
            self.brows.append((br, (ex, ey - eye_r * .25, ez + eye_r * 1.25), 1 if ex > 0 else -1))
        self.eye_r = eye_r
        self.beak = beak
        mx, my, mz = mouth_at
        self.mouth_base = (mx, my, mz)
        self.mouth_w = mouth_w
        ink = mat("mouth_ink", INK, rough=.5, sss=0, coat=0)
        self.closed = arc_curve(f"{name}_mouthc", head, mouth_w, mouth_w * .12, ink, mouth_at)
        dark = mat("mouth_dark", [110, 36, 62], rough=.5, sss=0, coat=0)
        tng = mat("tongue", [255, 128, 150], rough=.5, sss=.1, coat=0)
        self.open = prim(f"{name}_mouth", "sphere", dark, head, loc=(mx, my, mz), scale=(mouth_w * .75, mouth_w * .3, mouth_w * .5),
                         outline=True, shadow=False)
        prim(f"{name}_tongue", "sphere", tng, self.open, loc=(0, -.35, -.45), scale=(.6, .55, .4), outline=False, shadow=False)
        if teeth:
            prim(f"{name}_teeth", "cube", white, self.open, loc=(0, -.75, .62), scale=(.32, .12, .2), outline=False, shadow=False)

    def apply(self, emo, eyes_closed, mouth, t):
        op, raise_, tilt, smile, look = EMO.get(emo, EMO["happy"])
        r = self.eye_r
        happy_shut = emo == "proud" or (emo == "excited" and mouth > .5 and int(t * 3) % 5 == 0)
        shut = eyes_closed or happy_shut
        for (g, lk, ez), lid in zip(self.eyes, self.lids):
            for o in [g] + list(g.children_recursive):
                o.hide_render = shut
            lid.hide_render = not shut
            if shut:                                    # ^ ^ for a proud/laughing squeeze, a soft curve for a blink
                set_arc(lid, r * .62, -.7 if happy_shut else .25)
            g.scale = (1, 1, max(.05, op))
            lk.location = (look[0] * r * .35, 0, look[1] * r * .35)
        for i, (br, (bx, by, bz), side) in enumerate(self.brows):
            extra = .18 if emo == "thinking" and side > 0 else (-.04 if emo == "thinking" else 0)
            br.location = (bx, by, bz + (raise_ + extra) * r - (0 if not eyes_closed else .05 * r))
            br.rotation_euler = (0, side * tilt * .95, 0)        # tilt > 0: inner ends up (sad / worried)
        m = max(0.0, min(1.0, mouth))
        talking = m > .12
        if self.beak is not None:
            self.beak.rotation_euler = (-.55 * m if talking else 0, 0, 0)
        def show_open(on):
            for o in [self.open] + list(self.open.children_recursive):
                o.hide_render = not on
        if talking or emo in ("surprised",) or (emo == "excited" and m > .02):
            self.closed.hide_render = True
            show_open(True)
            h = .25 + .75 * (m if talking else (.55 if emo == "surprised" else .3))
            wk = .6 if emo == "surprised" else (1.0 if smile >= 0 else .8)
            self.open.scale = (self.mouth_w * .75 * wk, self.mouth_w * .3, self.mouth_w * .5 * h)
        else:
            self.closed.hide_render = False
            show_open(False)
            set_arc(self.closed, self.mouth_w * (.85 if smile > 0 else .65), smile)
        if self.beak is not None and not talking:
            self.closed.hide_render = True
            show_open(False)


# ================================================================= characters
POSE = {"down": (.32, 0), "wave": (2.5, .25), "up": (2.75, 0), "point": (1.45, .5), "clap": (.9, 1.0)}


class Char:
    """A built character: root (feet at origin, ~1 unit tall), a body group for squash/bob, face, arms."""

    def __init__(self, cid, spec):
        self.cid = cid
        self.root = empty(f"{cid}_root")
        self.body = empty(f"{cid}_body", self.root)
        self.arms = []
        self.face = None
        self.extra_anim = []
        sp = spec.get("species") or "bear"
        build = BUILDERS.get(sp) or (build_human if spec.get("kind") == "human" else build_animal)
        build(self, spec)
        self.height = spec.get("_height", 1.0)
        self.hide(True)

    def arm(self, side, shoulder, length, radius, m, hand_m=None):
        piv = empty(f"{self.cid}_arm{side}", self.body, shoulder)
        prim(f"{self.cid}_armm{side}", "sphere", m, piv, loc=(0, 0, -length / 2), scale=(radius, radius, length / 2 + radius * .4))
        prim(f"{self.cid}_hand{side}", "sphere", hand_m or m, piv, loc=(0, 0, -length), scale=(radius * 1.25,) * 3)
        self.arms.append((piv, side))

    def pose_arms(self, arms, t, k):
        for piv, side in self.arms:
            a, fwd = POSE.get(arms, POSE["down"])
            pose = arms
            if arms == "point" and side < 0:
                a, fwd = POSE["down"]
            if arms == "wave" and side < 0:
                a, fwd = POSE["down"]
            ang = a + (math.sin(t * 9 + k) * .28 if pose == "wave" and side > 0 else 0)
            if arms == "clap":
                ang += math.sin(t * 14) * .12
            piv.rotation_euler = (-fwd, side * ang, 0)

    def hide(self, h):
        for o in [self.root] + list(self.root.children_recursive):
            o.hide_render = h
        if not h and self.face:
            pass

    def apply(self, st, t):
        # st: [cid, x, hop, mouth, emo, eyes_closed, arms, look, appear_k, speaking, scale, sway]
        _, x, hop, mouth, emo, closed, arms, look, k, speaking, scale, sway = st
        self.hide(False)
        hgt = scale * 3.24 / self.height
        squash = 1 + (mouth * .03 if speaking else 0)
        self.root.location = (x, 0.0, hop)
        self.root.scale = (hgt * k, hgt * k, hgt * k * squash)
        self.root.rotation_euler = (0, 0, look * .3)
        self.body.location = (sway, 0, math.sin(t * 2.4 + len(self.cid)) * .008)
        self.pose_arms(arms, t, len(self.cid))
        if self.face:
            self.face.apply(emo, closed, mouth if speaking else 0.0, t)
        for fn in self.extra_anim:
            fn(t, st)


def body_part(c, name, kind, rgb, loc, scale, rot=(0, 0, 0), **kw):
    return prim(f"{c.cid}_{name}", kind, mat(f"{c.cid}_{name}", rgb, **{k: v for k, v in kw.items() if k in ('rough', 'sss', 'coat', 'emit', 'sheen')}),
                c.body, loc, scale, rot, outline=kw.get("outline", True))


def C(spec, k, default):
    v = (spec.get("colors") or {}).get(k)
    return list(v) if v else default


def build_frog(c, s):
    body, acc, belly = C(s, "body", [60, 196, 160]), C(s, "accent", [255, 140, 50]), C(s, "belly", [232, 250, 205])
    for sx in (-1, 1):
        body_part(c, f"haunch{sx}", "sphere", body, (sx * .3, .04, .15), (.2, .2, .17))
        body_part(c, f"foot{sx}", "sphere", body, (sx * .3, -.12, .03), (.17, .2, .05))
        for j, dx in enumerate((-.08, 0, .08)):
            body_part(c, f"toe{sx}{j}", "sphere_lo", lighten(acc, .25), (sx * .3 + dx, -.3, .04), (.045, .045, .04), outline=False)
    body_part(c, "torso", "sphere", body, (0, 0, .34), (.36, .3, .3))
    body_part(c, "belly", "sphere", belly, (0, -.13, .32), (.25, .18, .23), outline=False)
    head = empty(f"{c.cid}_head", c.body, (0, -.02, .68))
    prim(f"{c.cid}_headm", "sphere", mat(f"{c.cid}_skin", body), head, (0, 0, 0), (.44, .34, .24))
    prim(f"{c.cid}_chin", "sphere", mat(f"{c.cid}_bellyh", belly), head, (0, -.12, -.06), (.32, .2, .13), outline=False)
    for sx in (-1, 1):
        prim(f"{c.cid}_dome{sx}", "sphere", mat(f"{c.cid}_skin", body), head, (sx * .19, -.02, .2), (.15, .14, .14))
        for d, (dx, dz, r) in enumerate(((-.3, .05, .03), (.32, -.02, .025))):
            prim(f"{c.cid}_spot{sx}{d}", "sphere_lo", mat("spot", darken(body, .18)), head, (sx * (.3 + dx * .1), -.27, dz), (r, r * .6, r), outline=False)
    c.face = Face(c.cid, head, [(-.19, -.13, .22), (.19, -.13, .22)], .105, (0, -.31, -.06), .17, body, iris=(196, 120, 30))
    prim(f"{c.cid}_scarf", "torus", mat(f"{c.cid}_scarf", acc, sheen=.4), c.body, (0, 0, .47), (.33, .28, .27))
    prim(f"{c.cid}_knot", "sphere", mat(f"{c.cid}_scarf", acc, sheen=.4), c.body, (.17, -.26, .45), (.07, .05, .06))
    prim(f"{c.cid}_tail1", "sphere", mat(f"{c.cid}_scarf", acc, sheen=.4), c.body, (.25, -.22, .37), (.045, .03, .09), (0, -.7, 0))
    for sx in (-1, 1):
        c.arm(sx, (sx * .36, -.08, .46), .24, .06, mat(f"{c.cid}_skin", body))
    c.extra = head
    s["_height"] = 1.05


def build_penguin(c, s):
    body, acc, belly = C(s, "body", [70, 140, 230]), C(s, "accent", [255, 160, 40]), C(s, "belly", [250, 250, 255])
    for sx in (-1, 1):
        body_part(c, f"foot{sx}", "sphere", acc, (sx * .13, -.08, .03), (.11, .15, .04))
    body_part(c, "torso", "sphere", body, (0, 0, .48), (.36, .33, .46))
    body_part(c, "belly", "sphere", belly, (0, -.14, .38), (.26, .2, .3), outline=False)
    head = empty(f"{c.cid}_head", c.body, (0, 0, .62))
    for sx in (-1, 1):
        prim(f"{c.cid}_mask{sx}", "sphere", mat(f"{c.cid}_belly", belly), head, (sx * .11, -.24, .02), (.13, .1, .13), outline=False)
    for j, (dx, rz) in enumerate(((-.03, .3), (.03, 0), (.08, -.4))):
        prim(f"{c.cid}_tuft{j}", "cone", mat(f"{c.cid}_body", body), head, (dx, 0, .34), (.04, .04, .12), (0, rz, 0))
    beak_up = prim(f"{c.cid}_beak", "cone", mat(f"{c.cid}_beak", acc, coat=.5), head, (0, -.33, -.04), (.06, .06, .11), (math.pi / 2, 0, 0))
    lower = empty(f"{c.cid}_beakpiv", head, (0, -.3, -.07))
    prim(f"{c.cid}_beaklo", "cone", mat(f"{c.cid}_beak", darken(acc, .1), coat=.5), lower, (0, -.04, -.01), (.045, .045, .08), (math.pi / 2, 0, 0))
    c.face = Face(c.cid, head, [(-.11, -.31, .05), (.11, -.31, .05)], .085, (0, -.36, -.06), .07, body, iris=(46, 78, 150), beak=lower)
    for sx in (-1, 1):
        c.arm(sx, (sx * .37, -.04, .58), .3, .07, mat(f"{c.cid}_body", darken(body, .1)))
    s["_height"] = 1.0


def build_bunny(c, s):
    body, acc, belly = C(s, "body", [255, 170, 200]), C(s, "accent", [255, 225, 90]), C(s, "belly", [255, 235, 242])
    inner = [255, 128, 168]
    for sx in (-1, 1):
        body_part(c, f"foot{sx}", "sphere", body, (sx * .11, -.08, .03), (.09, .15, .045))
    body_part(c, "torso", "sphere", body, (0, 0, .24), (.2, .18, .22))
    body_part(c, "belly", "sphere", belly, (0, -.1, .22), (.13, .1, .15), outline=False)
    body_part(c, "tail", "sphere", lighten(body, .6), (0, .18, .16), (.07, .07, .07), sheen=.8)
    head = empty(f"{c.cid}_head", c.body, (0, 0, .58))
    prim(f"{c.cid}_headm", "sphere", mat(f"{c.cid}_skin", body), head, (0, 0, 0), (.27, .24, .23))
    prim(f"{c.cid}_muzzle", "sphere", mat(f"{c.cid}_muz", belly), head, (0, -.2, -.07), (.1, .06, .07), outline=False)
    prim(f"{c.cid}_nose", "sphere_lo", mat("pinknose", [240, 100, 140]), head, (0, -.25, -.02), (.03, .02, .022), outline=False)
    ears = []
    for sx, rot in ((-1, (0, .18, 0)), (1, (0, -.9, 0))):
        piv = empty(f"{c.cid}_earp{sx}", head, (sx * .1, 0, .17))
        piv.rotation_euler = rot
        prim(f"{c.cid}_ear{sx}", "sphere", mat(f"{c.cid}_skin", body), piv, (0, 0, .2), (.06, .04, .22))
        prim(f"{c.cid}_earin{sx}", "sphere", mat("innerear", inner), piv, (0, -.03, .2), (.035, .02, .16), outline=False)
        ears.append((piv, sx, rot))
    for i in range(5):
        a = i * 2 * math.pi / 5
        prim(f"{c.cid}_petal{i}", "sphere_lo", mat(f"{c.cid}_flower", acc), head, (-.18 + math.cos(a) * .04, -.12, .2 + math.sin(a) * .04), (.03, .015, .03), outline=False)
    prim(f"{c.cid}_fc", "sphere_lo", mat("flowerc", [255, 150, 60]), head, (-.18, -.14, .2), (.018, .01, .018), outline=False)
    c.face = Face(c.cid, head, [(-.1, -.17, .04), (.1, -.17, .04)], .085, (0, -.23, -.12), .06, body, iris=(120, 60, 110), lashes=True, teeth=True)
    for sx in (-1, 1):
        c.arm(sx, (sx * .17, -.02, .36), .17, .04, mat(f"{c.cid}_skin", body))

    def ears_anim(t, st, ears=ears):
        emo = st[4]
        for piv, sx, rot in ears:
            if emo in ("sad", "worried", "sleepy"):
                piv.rotation_euler = (0, sx * -1.2, 0)
            elif emo in ("excited", "surprised"):
                piv.rotation_euler = (0, sx * -.1, 0)
            else:
                piv.rotation_euler = (rot[0], rot[1] + math.sin(t * 2 + sx) * .04, rot[2])
    c.extra_anim.append(ears_anim)
    s["_height"] = 1.12


def build_dino(c, s):
    body, acc, belly = C(s, "body", [110, 200, 110]), C(s, "accent", [250, 210, 80]), C(s, "belly", [215, 245, 190])
    for sx in (-1, 1):
        body_part(c, f"leg{sx}", "sphere", body, (sx * .17, 0, .12), (.13, .14, .14))
        body_part(c, f"foot{sx}", "sphere", body, (sx * .17, -.06, .03), (.13, .16, .05))
    body_part(c, "torso", "sphere", body, (0, 0, .4), (.34, .3, .34))
    body_part(c, "belly", "sphere", belly, (0, -.15, .38), (.24, .17, .26), outline=False)
    tail = [(.25, .2, .22, .14), (.42, .3, .14, .11), (.56, .35, .08, .08), (.66, .38, .05, .05)]
    for i, (x, y, z, r) in enumerate(tail):
        body_part(c, f"tail{i}", "sphere", body, (x, y, z), (r, r, r))
    for i, (x, z) in enumerate(((0, .76), (0, .66), (.05, .5), (.15, .3))):
        body_part(c, f"plate{i}", "cone", acc, (x, .26, z), (.06, .03, .1), (-.6, 0, 0))
    head = empty(f"{c.cid}_head", c.body, (0, -.06, .82))
    prim(f"{c.cid}_headm", "sphere", mat(f"{c.cid}_skin", body), head, (0, 0, 0), (.28, .25, .2))
    prim(f"{c.cid}_snout", "sphere", mat(f"{c.cid}_bel", belly), head, (0, -.17, -.06), (.2, .12, .1), outline=False)
    c.face = Face(c.cid, head, [(-.11, -.2, .07), (.11, -.2, .07)], .08, (0, -.29, -.07), .11, body, iris=(110, 70, 40), teeth=True)
    for sx in (-1, 1):
        c.arm(sx, (sx * .34, -.1, .54), .2, .06, mat(f"{c.cid}_skin", body))
    s["_height"] = 1.08


def build_fox(c, s):
    body, acc, belly = C(s, "body", [250, 140, 60]), C(s, "accent", [90, 170, 220]), C(s, "belly", [255, 245, 230])
    dark = [90, 50, 40]
    for sx in (-1, 1):
        body_part(c, f"leg{sx}", "sphere", dark, (sx * .09, 0, .08), (.06, .07, .09))
    body_part(c, "torso", "sphere", body, (0, 0, .28), (.19, .17, .22))
    body_part(c, "belly", "sphere", belly, (0, -.1, .27), (.12, .09, .15), outline=False)
    body_part(c, "tail", "sphere", body, (.24, .12, .3), (.1, .1, .22), (0, -.7, 0))
    body_part(c, "tailtip", "sphere", belly, (.36, .14, .44), (.07, .07, .08), outline=False)
    body_part(c, "pack", "cube", acc, (0, .17, .32), (.14, .08, .15))
    head = empty(f"{c.cid}_head", c.body, (0, -.02, .63))
    prim(f"{c.cid}_headm", "sphere", mat(f"{c.cid}_skin", body), head, (0, 0, 0), (.24, .21, .2))
    prim(f"{c.cid}_muz", "sphere", mat(f"{c.cid}_muzz", belly), head, (0, -.17, -.07), (.11, .1, .07), outline=False)
    prim(f"{c.cid}_nose", "sphere_lo", mat("nose", [30, 20, 25], coat=.8), head, (0, -.27, -.04), (.03, .02, .022), outline=False)
    for sx in (-1, 1):
        prim(f"{c.cid}_ear{sx}", "cone", mat(f"{c.cid}_skin", body), head, (sx * .14, 0, .2), (.08, .05, .16), (0, sx * -.3, 0))
        prim(f"{c.cid}_eart{sx}", "cone", mat("eartip", dark), head, (sx * .17, -.005, .3), (.04, .03, .06), (0, sx * -.3, 0), outline=False)
        prim(f"{c.cid}_ruff{sx}", "sphere", mat(f"{c.cid}_muzz", belly), head, (sx * .19, -.08, -.1), (.07, .05, .06), outline=False)
    c.face = Face(c.cid, head, [(-.09, -.17, .04), (.09, -.17, .04)], .075, (0, -.25, -.11), .05, body, iris=(90, 60, 40), lashes=True)
    for sx in (-1, 1):
        c.arm(sx, (sx * .17, -.02, .4), .16, .04, mat(f"{c.cid}_skin", body), mat("paw", dark))
    s["_height"] = 1.0


def build_owl(c, s):
    body, acc, belly = C(s, "body", [150, 110, 200]), C(s, "accent", [255, 200, 90]), C(s, "belly", [230, 215, 250])
    for sx in (-1, 1):
        body_part(c, f"foot{sx}", "sphere", acc, (sx * .1, -.12, .03), (.07, .09, .035))
    body_part(c, "torso", "sphere", body, (0, 0, .46), (.34, .3, .44))
    body_part(c, "belly", "sphere", belly, (0, -.14, .38), (.23, .17, .27), outline=False)
    head = empty(f"{c.cid}_head", c.body, (0, -.04, .66))
    prim(f"{c.cid}_disc", "sphere", mat(f"{c.cid}_disc", lighten(body, .45)), head, (0, -.2, 0), (.27, .08, .17), outline=False)
    for sx in (-1, 1):
        prim(f"{c.cid}_tuft{sx}", "cone", mat(f"{c.cid}_body", body), head, (sx * .2, 0, .21), (.06, .05, .12), (0, sx * -.4, 0))
        prim(f"{c.cid}_glass{sx}", "torus", mat("gold", [230, 180, 60], rough=.2, coat=1, sss=0), head, (sx * .11, -.27, .03),
             (.085, .085, .085), (math.pi / 2, 0, 0), outline=False)
    lower = empty(f"{c.cid}_beakpiv", head, (0, -.27, -.09))
    prim(f"{c.cid}_beak", "cone", mat("owlbeak", acc), head, (0, -.29, -.06), (.035, .035, .07), (-math.pi / 2 - .3, 0, 0))
    c.face = Face(c.cid, head, [(-.11, -.29, .03), (.11, -.29, .03)], .07, (0, -.31, -.1), .05, body, iris=(150, 90, 40), beak=lower)
    for sx in (-1, 1):
        c.arm(sx, (sx * .36, -.04, .58), .28, .07, mat(f"{c.cid}_wing", darken(body, .12)))
    s["_height"] = 1.0


def build_sun(c, s):
    col = C(s, "body", [255, 205, 60])
    acc = C(s, "accent", [255, 150, 40])
    head = empty(f"{c.cid}_head", c.body, (0, 0, .5))
    prim(f"{c.cid}_core", "sphere", mat("suncore", col, emit=.6, sss=0, coat=.3), head, (0, 0, 0), (.36, .2, .36))
    rays = []
    for i in range(12):
        a = i * 2 * math.pi / 12
        piv = empty(f"{c.cid}_rayp{i}", head)
        piv.rotation_euler = (0, -a, 0)
        prim(f"{c.cid}_ray{i}", "cone", mat("sunray", acc, emit=.4, sss=0), piv, (0, .02, .48), (.08, .04, .13))
        rays.append(piv)
    c.face = Face(c.cid, head, [(-.12, -.18, .06), (.12, -.18, .06)], .075, (0, -.2, -.1), .1, col, iris=(110, 70, 40))

    def spin(t, st, rays=rays):
        for i, p in enumerate(rays):
            p.rotation_euler = (0, -(i * 2 * math.pi / 12) - t * .3, 0)
    c.extra_anim.append(spin)
    s["_height"] = 1.0


EARS = {"pointy": "cone", "round": "sphere", "big_round": "sphere", "long": "long", "floppy": "floppy", "tufts": "cone",
        "antennae": "antennae", "elephant": "elephant", "round_side": "sphere", "round_dark": "sphere"}


def build_animal(c, s):
    main = s.get("main") or C(s, "main", [200, 150, 100])
    belly = s.get("belly") or lighten(main, .5)
    acc = s.get("accent") or [255, 200, 60]
    size = float(s.get("size") or 1.0)
    for sx in (-1, 1):
        body_part(c, f"foot{sx}", "sphere", darken(main, .1), (sx * .11, -.06, .04), (.08, .11, .05))
    body_part(c, "torso", "sphere", main, (0, 0, .3), (.24, .21, .27))
    body_part(c, "belly", "sphere", belly, (0, -.12, .28), (.16, .12, .19), outline=False)
    head = empty(f"{c.cid}_head", c.body, (0, -.02, .7))
    prim(f"{c.cid}_headm", "sphere", mat(f"{c.cid}_skin", main), head, (0, 0, 0), (.27, .24, .23))
    face = s.get("face", "flat")
    beak = None
    if face in ("muzzle", "snout", "long_snout"):
        L = .14 if face == "long_snout" else .09
        prim(f"{c.cid}_muz", "sphere", mat(f"{c.cid}_bel", belly), head, (0, -.2 - L * .4, -.06), (.11, .06 + L, .08), outline=False)
        prim(f"{c.cid}_nose", "sphere_lo", mat("nose", [40, 28, 34], coat=.8), head, (0, -.27 - L * .8, -.03), (.035, .025, .025), outline=False)
    elif face in ("beak", "duck_bill"):
        beak = empty(f"{c.cid}_beakpiv", head, (0, -.25, -.06))
        prim(f"{c.cid}_beak", "cone", mat("beak", [255, 170, 50]), head, (0, -.29, -.04), (.05, .05, .09), (math.pi / 2, 0, 0))
    elif face == "trunk":
        prim(f"{c.cid}_trunk", "sphere", mat(f"{c.cid}_skin", main), head, (0, -.27, -.14), (.05, .05, .16), (.4, 0, 0))
    ears = EARS.get(s.get("ears", "round"), "none" if s.get("ears") == "none" else "sphere")
    for sx in (-1, 1):
        if ears == "cone":
            prim(f"{c.cid}_ear{sx}", "cone", mat(f"{c.cid}_skin", main), head, (sx * .15, 0, .2), (.07, .05, .13), (0, sx * -.3, 0))
        elif ears == "sphere":
            prim(f"{c.cid}_ear{sx}", "sphere", mat(f"{c.cid}_skin", main), head, (sx * .19, .02, .17), (.08, .04, .08))
        elif ears == "long":
            prim(f"{c.cid}_ear{sx}", "sphere", mat(f"{c.cid}_skin", main), head, (sx * .09, 0, .36), (.05, .035, .2), (0, sx * -.15, 0))
        elif ears == "floppy":
            prim(f"{c.cid}_ear{sx}", "sphere", mat(f"{c.cid}_skin", darken(main, .1)), head, (sx * .25, 0, .02), (.06, .04, .15), (0, sx * .5, 0))
        elif ears == "elephant":
            prim(f"{c.cid}_ear{sx}", "sphere", mat(f"{c.cid}_skin", main), head, (sx * .3, .03, 0), (.18, .03, .2))
        elif ears == "antennae":
            prim(f"{c.cid}_ant{sx}", "sphere", mat("ant", [50, 40, 50]), head, (sx * .08, 0, .3), (.012, .012, .1))
    extras = s.get("extras") or []
    if "mane" in extras:
        prim(f"{c.cid}_mane", "torus", mat("mane", darken(main, .25), sheen=.6), head, (0, .02, 0), (.3, .3, .26), (math.pi / 2, 0, 0))
    if "horns" in extras or "unicorn_horn" in extras:
        for sx in ((0,) if "unicorn_horn" in extras else (-1, 1)):
            prim(f"{c.cid}_horn{sx}", "cone", mat("horn", [250, 235, 200]), head, (sx * .1, 0, .26), (.035, .035, .1))
    if "shell" in extras:
        body_part(c, "shell", "sphere", darken(main, .3), (0, .12, .35), (.27, .18, .25))
    if "wings" in extras:
        for sx in (-1, 1):
            body_part(c, f"wing{sx}", "sphere", darken(main, .1), (sx * .26, .05, .35), (.05, .12, .18))
    if "spots" in extras:
        for i, (dx, dz) in enumerate(((-.15, .4), (.12, .3), (.05, .48))):
            body_part(c, f"spotx{i}", "sphere_lo", darken(main, .3), (dx, -.16, dz), (.04, .02, .04), outline=False)
    tail = s.get("tail", "none")
    if tail in ("bushy", "thick", "fish"):
        body_part(c, "tail", "sphere", main, (.2, .14, .25), (.07, .07, .17), (0, -.7, 0))
    elif tail in ("thin", "curly"):
        body_part(c, "tail", "sphere", main, (.18, .14, .2), (.025, .025, .13), (0, -.9, 0))
    c.face = Face(c.cid, head, [(-.1, -.19, .05), (.1, -.19, .05)], .08, (0, -.27, -.1), .07, main, beak=beak)
    for sx in (-1, 1):
        c.arm(sx, (sx * .21, -.02, .45), .17, .045, mat(f"{c.cid}_skin", main))
    s["_height"] = 1.0 / max(.7, size) * 1.0


def build_human(c, s):
    skin = s.get("skin_rgb") or [200, 150, 105]
    hair = s.get("hair_rgb") or [40, 35, 45]
    shirt = s.get("main") or [90, 150, 230]
    acc = s.get("accent") or [255, 200, 60]
    for sx in (-1, 1):
        body_part(c, f"leg{sx}", "sphere", darken(shirt, .35), (sx * .07, 0, .12), (.06, .06, .13))
        body_part(c, f"shoe{sx}", "sphere", [70, 50, 50], (sx * .07, -.04, .02), (.06, .08, .035))
    body_part(c, "torso", "sphere", shirt, (0, 0, .36), (.17, .14, .2), sheen=.3)
    head = empty(f"{c.cid}_head", c.body, (0, -.02, .72))
    prim(f"{c.cid}_headm", "sphere", mat(f"{c.cid}_skin", skin, sss=.3), head, (0, 0, 0), (.22, .2, .23))
    style = s.get("hair", "short")
    hm = mat(f"{c.cid}_hair", hair, sheen=.5, rough=.6)
    if style != "bald":
        prim(f"{c.cid}_hair", "sphere", hm, head, (0, .06, .1), (.23, .19, .17))
    if style in ("long", "braids", "ponytail"):
        prim(f"{c.cid}_hairb", "sphere", hm, head, (0, .1, -.12), (.2, .1, .22))
    if style == "bun":
        prim(f"{c.cid}_bun", "sphere", hm, head, (0, .06, .26), (.09, .09, .09))
    if style == "afro":
        prim(f"{c.cid}_afro", "sphere", hm, head, (0, .04, .08), (.3, .26, .28))
    if s.get("outfit") == "crown":
        prim(f"{c.cid}_crown", "cyl", mat("gold", [230, 180, 60], rough=.2, coat=1, sss=0), head, (0, 0, .24), (.13, .13, .05))
    elif s.get("outfit") in ("wizard_hat",):
        prim(f"{c.cid}_hat", "cone", mat("hat", acc), head, (0, 0, .35), (.17, .17, .3))
    c.face = Face(c.cid, head, [(-.08, -.18, .02), (.08, -.18, .02)], .065, (0, -.2, -.1), .06, skin, iris=(80, 52, 40))
    for sx in (-1, 1):
        c.arm(sx, (sx * .17, -.02, .48), .2, .04, mat(f"{c.cid}_shirt", shirt), mat(f"{c.cid}_skin", skin, sss=.3))
    s["_height"] = 1.0


BUILDERS = {"frog": build_frog, "penguin": build_penguin, "bunny": build_bunny, "dinosaur": build_dino, "fox": build_fox,
            "owl": build_owl, "sun": build_sun}


# ================================================================= sets
def sky_world(top, bottom, strength=1.0):
    w = bpy.data.worlds.new("sky")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = .0
    ramp.color_ramp.elements[0].color = srgb(bottom)
    ramp.color_ramp.elements[1].position = .55
    ramp.color_ramp.elements[1].color = srgb(top)
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength * .75
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return w


class Set:
    def __init__(self, sid, spec):
        self.sid = sid
        self.coll = bpy.data.collections.new(f"set_{sid}")
        SC.collection.children.link(self.coll)
        prev = bpy.context.view_layer.active_layer_collection
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[self.coll.name]
        sky = spec.get("sky") or [[140, 205, 255], [215, 240, 255]]
        self.dark = bool(spec.get("dark"))
        self.world = sky_world(sky[0], sky[1], .9 if not self.dark else .35)
        self.indoor = "wall" in spec
        build_set(sid, spec)
        bpy.context.view_layer.active_layer_collection = prev
        self.show(False)

    def show(self, on):
        self.coll.hide_render = not on
        if on:
            SC.world = self.world


def ground_mat(rgb):
    return mat(f"ground_{tuple(rgb)}", rgb, rough=.85, sss=0, coat=0, sheen=.3)


def tree(x, y, s, col=(110, 200, 100)):
    trunk = mat("trunk", [140, 95, 60], rough=.8, sss=0, coat=0)
    leaf = mat(f"leaf{col}", list(col), rough=.7, sss=.2, coat=0, sheen=.3)
    prim("trunk", "cyl", trunk, None, (x, y, s * .5), (s * .12, s * .12, s * 1.0))
    for i, (dx, dz, r) in enumerate(((0, 1.25, .62), (-.35, 1.0, .45), (.38, 1.02, .45), (0, 1.62, .42))):
        prim(f"leaf{i}", "sphere", leaf, None, (x + dx * s, y, dz * s), (r * s, r * s, r * s * .92))


def flower(x, y, s, col):
    prim("stem", "cyl", mat("stem", [90, 170, 80]), None, (x, y, s * .4), (s * .04, s * .04, s * .8), outline=False)
    for i in range(5):
        a = i * 2 * math.pi / 5
        prim("petal", "sphere_lo", mat(f"petal{col}", list(col)), None, (x + math.cos(a) * s * .18, y - .02, s * .85 + math.sin(a) * s * .18),
             (s * .14, s * .06, s * .14), outline=False)
    prim("fc", "sphere_lo", mat("fcen", [255, 210, 70]), None, (x, y - .05, s * .85), (s * .1, s * .06, s * .1), outline=False)


def house(x, y, s):
    prim("wall", "cube", mat("housewall", [255, 240, 210], rough=.8), None, (x, y, s * .55), (s * .55, s * .45, s * .55))
    prim("roof", "cone", mat("roof", [230, 80, 70], rough=.6), None, (x, y, s * 1.35), (s * .8, s * .6, s * .55), (0, 0, math.pi / 4))
    prim("door", "cube", mat("door", [150, 95, 60]), None, (x, y - s * .46, s * .3), (s * .13, s * .02, s * .25), outline=False)


def cloud(x, y, z, s):
    cm = mat("cloud", [255, 255, 255], rough=.9, sss=.4, coat=0, emit=.15)
    for i, (dx, dz, r) in enumerate(((0, 0, .5), (-.55, -.1, .38), (.55, -.08, .4), (.25, .22, .36))):
        prim("cloud", "sphere", cm, None, (x + dx * s, y, z + dz * s), (r * s, r * s * .7, r * s * .8), outline=False, shadow=False)


def fence(y, z0=0):
    wm = mat("fence", [255, 250, 240], rough=.7)
    for i in range(-11, 12):
        prim("post", "cube", wm, None, (i * 1.0, y, .55), (.07, .05, .55), outline=False)
    for zz in (.4, .8):
        prim("rail", "cube", wm, None, (0, y, zz), (11.5, .03, .05), outline=False)


def build_set(sid, spec):
    g = spec.get("ground") or [125, 205, 110]
    if spec.get("underwater"):
        prim("seabed", "cube", ground_mat(g), None, (0, 6, -.5), (40, 20, .5), outline=False)
        for i in range(10):
            x = -12 + i * 2.6
            prim("weed", "sphere", mat("weed", [70, 170, 100], sss=.3), None, (x, 3 + (i % 3), 1.2), (.15, .15, 1.3), outline=False)
        return
    if "wall" in spec:
        prim("floor", "cube", ground_mat(spec.get("floor") or [220, 180, 130]), None, (0, 4, -.25), (30, 12, .25), outline=False)
        prim("wall", "cube", mat("wall", spec["wall"], rough=.9, sss=0, coat=0), None, (0, 8.5, 6), (30, .2, 7), outline=False)
        if spec.get("window"):
            prim("window", "cube", mat("window", [190, 225, 255], emit=.4, rough=.2), None, (5, 8.25, 5.2), (1.6, .05, 1.2), outline=True)
        if spec.get("board"):
            prim("board", "cube", mat("board", [60, 110, 80], rough=.8), None, (-4, 8.25, 5), (3, .05, 1.6), outline=True)
        return
    # outdoor: flat stage in front, rolling hills behind, props from the 2D layout
    prim("ground", "cube", ground_mat(g), None, (0, 10, -.5), (60, 25, .5), outline=False)
    hills = spec.get("hills") or [lighten(g, .2)]
    for i, hc in enumerate(hills[:3]):
        for j in range(5):
            x = -24 + j * 12 + i * 5
            prim("hill", "sphere", ground_mat(hc), None, (x, 18 + i * 6, -3), (9, 5, 6 + i), outline=False, shadow=False)
    if spec.get("sea"):
        prim("sea", "cube", mat("sea", spec["sea"], rough=.15, sss=0, coat=.8), None, (0, 16, -.45), (60, 8, .5), outline=False)
    if spec.get("fence"):
        fence(2.5)
    for kind, px, py, ps in spec.get("props") or []:
        x = (px - .5) * VIEW_W * 1.15
        depth = 1.5 + (1 - py) * 10                     # higher on the 2D screen = further back
        s = ps * 9 * (1 + depth / 25)
        if kind == "tree":
            tree(x, depth, s * .55)
        elif kind == "flower":
            flower(x, depth * .4, s * .5, [255, 130, 170] if int(px * 10) % 2 else [255, 200, 70])
        elif kind == "house":
            house(x, depth + 2, s * .5)
        elif kind in ("ball", "shell", "block", "book", "carrot", "leaf"):
            prim(kind, "sphere", mat(kind, [255, 120, 90] if kind == "ball" else [250, 220, 200]), None, (x, depth * .4, .2), (.2, .2, .2))
    if spec.get("overlay") == "clouds" or spec.get("sky"):
        for i, (cx, cz, cs) in enumerate(((-7, 8.5, 1.2), (-2, 9.6, .9), (4, 8.9, 1.1), (9, 9.8, .8))):
            cloud(cx * 1.6, 30, cz * 1.9, cs * 2.2)


# ================================================================= lights + camera
sun = bpy.data.lights.new("key", "SUN")
sun.energy = 3.8
sun.angle = math.radians(12)
sun.color = (1.0, .96, .9)
sun_o = bpy.data.objects.new("key", sun)
SC.collection.objects.link(sun_o)
sun_o.rotation_euler = Euler((math.radians(52), math.radians(-18), math.radians(-30)))
fill = bpy.data.lights.new("fill", "AREA")
fill.energy = 900
fill.size = 18
fill.color = (.85, .9, 1.0)
fill_o = bpy.data.objects.new("fill", fill)
SC.collection.objects.link(fill_o)
fill_o.location = (0, -18, 9)
fill_o.rotation_euler = Euler((math.radians(70), 0, 0))
cam = bpy.data.cameras.new("cam")
cam.lens = FOCAL
cam.sensor_width = SENSOR
cam.clip_end = 300
cam_o = bpy.data.objects.new("cam", cam)
SC.collection.objects.link(cam_o)
SC.camera = cam_o
cam_o.rotation_euler = Euler((math.pi / 2, 0, 0))


def place_camera(cxf, cyf, zoom):
    """2D shot (centre as screen fractions, zoom) -> camera dolly. The wide shot (zoom 1) sees 16x9 units."""
    zoom = max(1.0, zoom)
    x = (cxf - .5) * VIEW_W
    z = (1 - cyf) * VIEW_H - GROUND_FRAC * VIEW_H
    cam_o.location = (x, -DIST / zoom, z)


# ================================================================= build everything + render
CHARS = {cid: Char(cid, spec) for cid, spec in JOB["cast"].items()}
SETS = {sid: Set(sid, spec) for sid, spec in JOB["sets"].items()}
FRAMES = JOB["frames"]
FIRST = JOB.get("first", 0)


def apply_frame(scene, *_):
    i = scene.frame_current - FIRST
    if i < 0 or i >= len(FRAMES):
        return
    st = FRAMES[i]
    t = st["t"]
    for sid, s in SETS.items():
        s.show(sid == st["set"])
    on = {c[0] for c in st["chars"]}
    for cid, ch in CHARS.items():
        if cid not in on:
            ch.hide(True)
    for c in st["chars"]:
        x = (c[1] - .5) * VIEW_W
        ch = CHARS.get(c[0])
        if ch:
            ch.apply([c[0], x] + c[2:], t)
    place_camera(*st["cam"])


bpy.app.handlers.frame_change_pre.clear()
bpy.app.handlers.frame_change_pre.append(apply_frame)
SC.frame_start = FIRST
SC.frame_end = JOB.get("last", FIRST + len(FRAMES) - 1)
SC.render.filepath = os.path.join(JOB["out_dir"], "f_")
SC.render.use_overwrite = False
SC.render.use_placeholder = True
print(f"[3d] engine {ENGINE}, {len(CHARS)} characters, {len(SETS)} sets, frames {SC.frame_start}-{SC.frame_end}", flush=True)
if JOB.get("still") is not None:
    SC.frame_set(int(JOB["still"]))
    SC.render.filepath = JOB["still_path"]
    bpy.ops.render.render(write_still=True)
else:
    bpy.ops.render.render(animation=True)
print("[3d] done", flush=True)
