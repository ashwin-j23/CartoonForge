"""3D episodes: the same script, voices, music, expressions and camera plan as the 2D renderer, but the world and the
cast are real 3D (Blender), rendered as soft vinyl-toy figures with cartoon outlines.

Pipeline
  1. voices + music (render/audio.py, shared)            -> soundtrack.wav + word/mouth timings
  2. Timeline (render/frame.py, shared)                   -> who is on screen, expressions, blinks, camera shots
  3. frame_state(tl, t) for every 3D frame                -> job.json
  4. Blender (backend/tools/blender, render/three_d/blender_scene.py) renders the 3D frames
  5. 2D HUD on top at the output rate (cards zoom with the camera; captions, banners, countdown, logo crisp)
  6. H.264 + loudness-normalised AAC

Speed: on CPU (this machine's sandbox) ~2 s per 960x540 frame, so 3D frames are rendered "on twos" (12 fps, like
stop-motion) by default; with an NVIDIA GPU Blender uses OptiX/CUDA automatically and 24 fps 1080p is practical.
Settings: render_3d_quality = draft (960x540 @ 12) | standard (1280x720 @ 12) | high (1920x1080 @ 24).
"""
from __future__ import annotations

import bisect
import json
import math
import multiprocessing as mp
import os
import pickle
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image

from ... import config
from ...kids import cast as castmod
from .. import expression, frame as fr

ROOT = Path(__file__).resolve().parents[3]                 # backend/
BLENDER = Path(os.getenv("BLENDER_BIN") or ROOT / "tools" / "blender" / "blender")
SCENE = Path(__file__).with_name("blender_scene.py")
QUALITY = {"draft": (960, 540, 12, 10), "standard": (1280, 720, 12, 14), "high": (1920, 1080, 24, 20)}
SIZE = {"hoppy": .9, "pip": .82, "mimi": .95, "bo": 1.12, "zuzu": .95, "nana": .95}
ARMS_FOR = fr.ARMS_FOR


def available() -> bool:
    return BLENDER.exists() and os.access(BLENDER, os.X_OK)


def _z_for(bottom_frac: float) -> float:
    """Screen fraction of a sprite's feet -> world height above the ground (ground at .93)."""
    return max(0.0, (.93 - bottom_frac) * 9.0)


def _ease_back(k):
    return fr.ease_out_back(k) if k < 1 else 1.0


def _eyes(t, seed, emo, since):
    switching = since is not None and 0 <= t - since < .09
    return bool(fr._blink(t, seed) or switching or (emo == "sleepy" and int(t) % 3 == 0))


def _arms(action, t):
    arms = ARMS_FOR.get(action, "down")
    if action == "dance":
        arms = "wave" if int(t * 2) % 2 else "up"
    elif action == "clap":
        arms = "clap" if int(t * 2.5) % 2 else "down"
    return arms


def _char(cid, xf, t, *, speaking, mouth, emo, since, action, look, appear, seed, energy, size=None, hop_extra=0.0):
    hop = hop_extra
    sway = 0.0
    if action == "jump" and speaking:
        ph = (t * 1.6 + seed * .1) % 1
        hop += math.sin(ph * math.pi) * .07 * min(1.5, energy) * 9
    elif action == "dance":
        sway = math.sin(t * math.pi * 1.4 + seed) * .02 * 9
        hop += abs(math.sin(t * math.pi * 1.4)) * .02 * 9
    k = _ease_back((t - appear) / .45) if appear is not None else 1.0
    return [cid, round(xf, 4), round(hop, 4), round(float(mouth) if speaking else 0.0, 3), emo,
            _eyes(t, seed, emo, since), _arms(action, t), look, round(max(0.0, k), 3), bool(speaking),
            size if size is not None else SIZE.get(cid, .95) * .86, round(sway, 4)]


def _sunny_entry(t, side, big, speaking, mouth, emo, since, action):
    size = .26 if big else .17
    x = .115 if side == "left" else .885
    y = .2 if big else .15
    return _char("sunny", x, t, speaking=speaking, mouth=mouth, emo=emo, since=since, action="idle", look=0,
                 appear=None, seed=1, energy=1, size=size / .36, hop_extra=_z_for(y + size / 2))


def frame_state(tl: fr.Timeline, t: float) -> dict:
    """Everything Blender needs for one frame (screen fractions; heights in world units)."""
    W, H = tl.W, tl.H
    fi = min(len(tl.mouth) - 1, int(t * tl.fps))
    mouth = float(tl.mouth[fi]) if fi >= 0 else 0.0
    energy = tl.pace["motion"]
    st = {"t": round(t, 4), "set": "meadow", "chars": [], "cam": [.5, .5, 1.0]}

    if t < tl.jingle - 0.5 or not tl.scenes:                       # intro: Sunny + the star
        st["set"] = "storybook" if tl.storybook and "storybook" in tl.__dict__.get("_3d_sets", ()) else "meadow"
        st["chars"].append(_char("sunny", .5, t, speaking=True, mouth=.55 + .45 * math.sin(t * 9), emo="excited",
                                 since=None, action="idle", look=0, appear=None, seed=1, energy=1, size=.42 / .36,
                                 hop_extra=_z_for(.52 + .21) + math.sin(t * 5) * .09))
        if t > .5:
            ph = ((t - .5) * 1.7) % 1
            hop = math.sin(ph * math.pi) * .08 * 9
            hx = .87 - min(1, (t - .5) / .6) * .03
            st["chars"].append(_char(castmod.STAR, hx, t, speaking=True, mouth=.6 if hop > .5 else .3, emo="excited",
                                     since=None, action="jump" if hop > .3 else "wave", look=-1, appear=None, seed=7,
                                     energy=1, size=.3 / .36, hop_extra=hop))
        st["cam"] = [.5, .5, 1.0 + (.06 * (t / max(1, tl.jingle)) if tl.pace["shot"] else 0)]
        st["mode"] = "intro"
        return st

    if t >= tl.outro:                                                 # end card: everyone waves
        for i, cid in enumerate(["pip", "mimi", castmod.STAR, "bo", "zuzu", "nana"]):
            st["chars"].append(_char(cid, .1 + i * .16, t, speaking=False, mouth=0, emo="happy", since=None,
                                     action="wave" if (int(t * 1.5) + i) % 2 else "idle", look=0,
                                     appear=tl.outro + i * .12, seed=i, energy=energy))
        st["mode"] = "outro"
        return st

    tq = fr._lookup_time(tl, t) if hasattr(fr, "_lookup_time") else t
    si, sc = tl.scene_at(tq)
    gi, seg = tl.seg_at(tq)
    if sc is None:
        sc, si = tl.scenes[0], 0
    data = tl.scene_data(sc)
    st["set"] = (seg or {}).get("set") or "meadow"
    speaker = data["speaker"]
    talking = sc["start"] <= t <= sc["voice_end"]
    in_pause = sc["kind"] == "question" and t > sc["voice_end"]
    track = expression.speaker_track(sc, data)
    emotion, emo_since = expression.at(track, t)
    card = data.get("card")
    on = [c for c in data.get("cast", []) if (c in castmod.CAST or c in tl.guests) and c != "sunny"][:3] or [castmod.STAR]
    xs = ({1: [.2], 2: [.13, .31], 3: [.09, .22, .35]} if card else {1: [.5], 2: [.36, .64], 3: [.27, .5, .73]})[len(on)]
    xs3 = ({1: [.22], 2: [.13, .33], 3: [.1, .25, .4]} if card else {1: [.5], 2: [.34, .66], 3: [.24, .5, .76]})[len(on)]
    side = fr._sunny_side(tl, sc["seg"]) if hasattr(fr, "_sunny_side") else "right"
    sx_speaker = xs[on.index(speaker)] if speaker in on else ((.115 if side == "left" else .885) if speaker == "sunny" else .5)
    for c, xf in zip(on, xs3):                       # 3D bodies are rounder than sprites: a little more room
        j = si
        while j > 0 and tl.scenes[j - 1]["seg"] == sc["seg"] and c in tl.scene_data(tl.scenes[j - 1]).get("cast", []):
            j -= 1
        first = tl.scenes[j]["start"] if tl.scenes[j]["seg"] == sc["seg"] else sc["start"]
        is_sp = c == speaker
        c_emo, c_since = (emotion, emo_since) if is_sp else expression.listener(track, sc, t, hash(c) % 7, in_pause)
        st["chars"].append(_char(c, xf, t, speaking=is_sp and talking, mouth=mouth, emo=c_emo, since=c_since,
                                 action=data.get("action", "idle") if is_sp else ("dance" if data.get("action") == "dance" else "idle"),
                                 look=0 if is_sp else (1 if sx_speaker > xf else -1),
                                 appear=first if seg and first > seg["start"] + .01 else None, seed=hash(c) % 7, energy=energy))
    s_emo, s_since = (emotion, emo_since) if speaker == "sunny" else expression.listener(track, sc, t, 1, in_pause)
    st["chars"].append(_sunny_entry(t, side, speaker == "sunny" and talking, speaker == "sunny" and talking, mouth,
                                    s_emo, s_since, data.get("action", "idle")))

    # the camera plan is the 2D one (same shots, cuts, drift and beat punches), turned into a 3D dolly
    try:
        shots = fr._shots(tl, si, sc, data, on, xs, card, speaker, W, H, side)
    except TypeError:
        shots = fr._shots(tl, si, sc, data, on, xs, card, speaker, W, H)
    k = max(0, bisect.bisect_right([s[0] for s in shots], t) - 1)
    shot = shots[k][1]
    name, (cx, cy, z) = shot[0], shot[1]
    fit = shot[2] if len(shot) > 2 else None
    s_start = shots[k][0]
    s_end = shots[k + 1][0] if k + 1 < len(shots) else sc["end"]
    prog = min(1.0, max(0.0, (t - s_start) / max(.3, s_end - s_start)))
    drift = (.05 if tl.pace["shot"] else .04) * fr.ease_in_out(prog)
    pan = (W * .015 if (k + si) % 2 else -W * .015) * (prog - .5) if name != "wide" else 0
    zoom = z + drift + fr._beat_pulse(tl, t)
    if name == "wide" and not tl.pace["shot"] and sc["kind"] != "question":
        zoom = 1.0
    x0, y0, w, h = fr._crop_box(cx + pan, cy, zoom, W, H, fit) if fit is not None else fr._crop_box(cx + pan, cy, zoom, W, H)
    st["cam"] = [round((x0 + w / 2) / W, 4), round((y0 + h / 2) / H, 4), round(W / w, 4)]
    st["mode"] = "scene"
    st["_crop"] = [x0, y0, w, h]
    return st


# ---------------------------------------------------------------- job
def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    return o


def cast_specs(script: dict) -> dict:
    from ..designer import normalize
    out = {cid: {"kind": "cast", "species": c["species"], "colors": {k: list(v) for k, v in c["colors"].items()}}
           for cid, c in castmod.CAST.items()}
    for g in script.get("characters") or []:
        if g.get("id") and g["id"] not in castmod.CAST:
            sp = normalize(g)
            out[g["id"]] = _jsonable({k: v for k, v in sp.items() if not str(k).startswith("_")})
    return out


def set_specs(script: dict) -> dict:
    from ..sets import SETS
    ids = {"meadow"} | {s.get("set") or "meadow" for s in script.get("segments", [])}
    return {sid: _jsonable(SETS.get(sid) or SETS["meadow"]) for sid in ids}


def run_blender(job: dict, workdir: Path, log=print, progress=None, total=None) -> None:
    jp = workdir / "job3d.json"
    jp.write_text(json.dumps(job, separators=(",", ":")))
    cmd = [str(BLENDER), "-b", "--factory-startup", "-noaudio", "--python", str(SCENE), "--", str(jp)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    done, last_t = 0, time.time()
    tail = []
    for line in p.stdout:
        tail = (tail + [line])[-40:]
        if line.startswith("[3d]"):
            log(line.strip()[5:])
        elif "Saved:" in line:
            done += 1
            if progress and total and time.time() - last_t > 5:
                progress("rendering 3D", 30 + int(50 * done / total))
                last_t = time.time()
    if p.wait() != 0:
        raise RuntimeError("Blender failed:\n" + "".join(tail[-15:]))


class TooSlow(RuntimeError):
    """This machine would take longer than the 3D budget (settings render_3d_max_minutes): render 2D instead."""


def seconds_per_frame(job: dict, workdir: Path, n: int = 4) -> float:
    """Render n sample frames spread over the episode and time the gap between them (Blender's start-up and scene
    build are left out). CPU-only machines are ~50x slower than a GPU, so this decides whether 3D is possible here."""
    frames = job["frames"]
    pick = [frames[round(i * (len(frames) - 1) / (n - 1))] for i in range(n)] if len(frames) >= n else frames
    calib = workdir / "calib3d"
    calib.mkdir(parents=True, exist_ok=True)
    jp = workdir / "calib3d.json"
    jp.write_text(json.dumps({**job, "out_dir": str(calib), "first": 0, "last": len(pick) - 1, "frames": pick},
                             separators=(",", ":")))
    p = subprocess.Popen([str(BLENDER), "-b", "--factory-startup", "-noaudio", "--python", str(SCENE), "--", str(jp)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    t0, saved = time.time(), []
    for line in p.stdout:
        if "Saved:" in line:
            saved.append(time.time())
    p.wait()
    shutil.rmtree(calib, ignore_errors=True)
    if p.returncode != 0 or not saved:
        raise RuntimeError("Blender could not render the sample frames")
    if len(saved) >= 2:
        return (saved[-1] - saved[0]) / (len(saved) - 1)
    return saved[0] - t0


# ---------------------------------------------------------------- HUD over the 3D picture
def hud(tl: fr.Timeline, t: float, base: Image.Image, st: dict) -> Image.Image:
    W, H = tl.W, tl.H
    OW, OH = tl.out_W, tl.out_H
    f = base if base.size == (OW, OH) else base.resize((OW, OH), Image.LANCZOS)
    f = f.convert("RGB")
    mode = st.get("mode")
    if mode == "intro":
        fr._logo(f, tl.channel, t, OW, OH, OH * .14)
        k = fr.ease_out((t - 1.2) / .6)
        if k > 0:
            ti = fr.fit_text(tl.title, int(OW * .8), int(OH * .07), fill=(255, 255, 255), stroke=fr.OUT)
            f.paste(ti, (int(OW / 2 - ti.width / 2), int(OH * .86 - ti.height / 2 + (1 - k) * OH * .1)), ti)
        return f
    if mode == "outro":
        lt = t - tl.outro
        fr._logo(f, tl.channel, lt, OW, OH, OH * .14)
        if tl.cta:
            k = fr.ease_out_back((lt - 1.0) / .5)
            if k > .02:
                ci = fr.fit_text(tl.cta, int(OW * .7), int(OH * .055), fill=(255, 255, 255), stroke=fr.OUT)
                pill = fr.rounded(ci.width + int(OH * .2), int(OH * .1), int(OH * .05), fr.palette.button(),
                                  outline=(255, 255, 255), width=4)
                pill.alpha_composite(ci, ((pill.width - ci.width) // 2, (pill.height - ci.height) // 2))
                if k < .99:
                    pill = pill.resize((max(1, int(pill.width * k)), max(1, int(pill.height * k))))
                f.paste(pill, (int(OW / 2 - pill.width / 2), int(OH * .3 - pill.height / 2)), pill)
        return f
    tq = fr._lookup_time(tl, t) if hasattr(fr, "_lookup_time") else t
    si, sc = tl.scene_at(tq)
    gi, seg = tl.seg_at(tq)
    if sc is None:
        sc, si = tl.scenes[0], 0
    data = tl.scene_data(sc)
    card = data.get("card")
    talking = sc["start"] <= t <= sc["voice_end"]
    in_pause = sc["kind"] == "question" and t > sc["voice_end"]
    if card:                                                    # the card lives in the world: it zooms with the camera
        appear_at = sc["start"]
        j = si
        while j > 0:
            prev = tl.scenes[j - 1]
            if prev["seg"] != sc["seg"] or tl.scene_data(prev).get("card") != card:
                break
            j -= 1
        appear_at = tl.scenes[j]["start"]
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fr.draw_card(layer, card, sc, t, W * .69, H * .47, int(W * .44), int(H * .64), appear_at)
        x0, y0, w, h = st.get("_crop") or (0, 0, W, H)
        layer = layer.resize((OW, OH), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))
        f.paste(layer, (0, 0), layer)
    if in_pause:
        kk = (t - sc["voice_end"]) / max(.1, sc["end"] - sc["voice_end"])
        fr._countdown(f, kk, OW * .5 if not card else OW * .69, OH * .13, OH * .06)
    if sc.get("sing") and tl.captions_song:
        fr._caption(f, sc["words"], t, OW, OH, True)
    elif tl.captions_all and talking:
        fr._caption(f, sc["words"], t, OW, OH, False)
    if seg:
        lt = t - seg["start"]
        if 0.3 < lt < 3.2 and seg["kind"] not in ("hello",):
            kb = fr.ease_out((lt - .3) / .5) if lt < 2.6 else 1 - fr.ease_in_out((lt - 2.6) / .6)
            fr._banner(f, seg["title"], kb, OW, OH, seg["kind"])
        to_end = seg["end"] - t                                   # a quick soft iris between segments (≤ 0.3 s)
        if gi < len(tl.segments) - 1 and to_end < .3:
            f = fr._iris(f, .85 * fr.ease_in_out(1 - to_end / .3))
        elif gi > 0 and lt < .3:
            f = fr._iris(f, .85 * (1 - fr.ease_in_out(lt / .3)))
    return f


def _hud_worker(args):
    tl_path, frames_dir, states_path, start, end, fps3d, fps, out = args
    with open(tl_path, "rb") as fh:
        tl = pickle.load(fh)
    with open(states_path, "rb") as fh:
        states = pickle.load(fh)
    cmd = [config.FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{tl.out_W}x{tl.out_H}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", config.X264_PRESET, "-tune", "animation",
           "-crf", str(config.X264_CRF), "-pix_fmt", "yuv420p", "-g", str(fps * 4), "-threads", "2", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    cache = {}
    lum = []
    for i in range(start, end):
        t = i / fps
        j = min(len(states) - 1, int(t * fps3d))
        if j not in cache:
            cache.clear()
            path = Path(frames_dir) / f"f_{j:04d}.png"
            if not path.exists():
                path = Path(frames_dir) / f"f_{j:05d}.png"
            cache[j] = Image.open(path).convert("RGB")
        im = hud(tl, t, cache[j], states[j])
        if i % 2 == 0:
            lum.append(float(np.asarray(im.resize((32, 18))).mean()))
        p.stdin.write(im.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return out, lum


def check_speed(script: dict, settings: dict, workdir: Path, log=print) -> None:
    """Raise TooSlow when this machine can't render the episode in 3D within render_3d_max_minutes."""
    from ..episode import estimate_audio
    rw, rh, fps3d, samples = QUALITY.get(settings.get("render_3d_quality") or "standard", QUALITY["standard"])
    snd = estimate_audio(script, 24)
    tl = fr.Timeline(script, snd, 1280, 720, 24, settings)
    tl._3d_sets = tuple(set_specs(script))
    n3 = int(snd["duration"] * fps3d) + 1
    sample = [frame_state(tl, snd["duration"] * (i + .5) / 4) for i in range(4)]
    job = {"W": rw, "H": rh, "fps": fps3d, "samples": samples, "engine": settings.get("render_3d_engine", "auto"),
           "outline": True, "cast": cast_specs(script), "sets": set_specs(script),
           "frames": [{k: v for k, v in st.items() if not k.startswith("_")} for st in sample]}
    workdir.mkdir(parents=True, exist_ok=True)
    per = seconds_per_frame(job, workdir)
    est, budget = per * n3 / 60, float(settings.get("render_3d_max_minutes", 120))
    log(f"3D speed here: {per:.1f} s a frame, about {est:.0f} min for {n3} frames (budget {budget:.0f} min)")
    if est > budget:
        raise TooSlow(f"3D would take about {est:.0f} min on this machine ({per:.1f} s a frame, budget {budget:.0f} min)")


def render_video(script: dict, settings: dict, workdir: Path, log=print, progress=None) -> dict:
    """Same contract as render/episode.py render(), but the picture is 3D."""
    from .. import audio as audiomod
    from ..episode import _size, flash_check, thumbnail
    if not available():
        raise RuntimeError(f"Blender not found at {BLENDER} (download it to backend/tools/blender or set BLENDER_BIN)")
    check_speed(script, settings, workdir, log)          # first: a 2D fallback mustn't record the voices twice
    W, H = _size(settings)
    fps = config.RENDER_FPS
    q = QUALITY.get(settings.get("render_3d_quality") or "standard", QUALITY["standard"])
    rw, rh, fps3d, samples = q
    wav = workdir / "soundtrack.wav"
    log("Recording voices and music…")
    snd = audiomod.build(script, settings, wav, fps, log)
    if progress:
        progress("rendering 3D", 25)
    tl = fr.Timeline(script, snd, W, H, fps, settings)
    tl._3d_sets = tuple(set_specs(script))
    n3 = int(snd["duration"] * fps3d) + 1
    log(f"Planning {n3} 3D frames ({rw}x{rh} @ {fps3d} fps)…")
    states = [frame_state(tl, i / fps3d) for i in range(n3)]
    frames_dir = workdir / "frames3d"
    frames_dir.mkdir(exist_ok=True)
    job = {"W": rw, "H": rh, "fps": fps3d, "out_dir": str(frames_dir), "first": 0, "last": n3 - 1, "samples": samples,
           "engine": settings.get("render_3d_engine", "auto"), "outline": True, "cast": cast_specs(script),
           "sets": set_specs(script), "frames": [{k: v for k, v in s.items() if not k.startswith("_")} for s in states]}
    t0 = time.time()
    run_blender(job, workdir, log, progress, n3)
    log(f"3D frames done in {(time.time() - t0) / 60:.1f} min")
    tl_path, st_path = workdir / "timeline3d.pkl", workdir / "states3d.pkl"
    with open(tl_path, "wb") as fh:
        pickle.dump(tl, fh)
    with open(st_path, "wb") as fh:
        pickle.dump(states, fh)
    total = int(snd["duration"] * fps)
    n = max(1, min(8, (os.cpu_count() or 4) // 2))
    bounds = [round(total * i / n) for i in range(n + 1)]
    jobs = [(str(tl_path), str(frames_dir), str(st_path), bounds[i], bounds[i + 1], fps3d, fps,
             str(workdir / f"part3d{i:02d}.mp4")) for i in range(n)]
    parts, lum = [], []
    with mp.get_context("fork").Pool(n) as pool:
        for out, l in pool.imap(_hud_worker, jobs):
            parts.append(out)
            lum += l
    lst = workdir / "parts3d.txt"
    lst.write_text("".join(f"file '{Path(p).name}'\n" for p in parts))
    video = workdir / "episode.mp4"
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(wav),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", "loudnorm=I=-15:TP=-1.5:LRA=11", "-ar", "48000",
                    "-ac", "2", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(video)],
                   check=True, cwd=workdir)
    thumb = workdir / "thumb.jpg"
    _thumb3d(tl, states, frames_dir, script, settings, thumb)
    shutil.rmtree(frames_dir, ignore_errors=True)
    return {"video": video, "thumb": thumb, "duration": snd["duration"], "segments": snd["segments"],
            "engines": snd["engines"], "flash": flash_check(lum, fps / 2), "W": W, "H": H, "fps": fps,
            "song_regions": snd["song_regions"],
            "scenes": [{k: sc.get(k) for k in ("seg", "idx", "speaker", "start", "end", "kind")} for sc in snd.get("scenes", [])]}


def _thumb3d(tl, states, frames_dir, script, settings, out: Path):
    """Thumbnail from the 3D render: the frame where the star is biggest on screen, with the title."""
    from ..episode import _thumb_words
    best, score = 0, -1
    for j, s in enumerate(states):
        if s.get("mode") != "scene":
            continue
        z = s["cam"][2]
        star = any(c[0] == castmod.STAR and c[9] for c in s["chars"])
        sc = z * (2 if star else 1)
        if sc > score:
            best, score = j, sc
    p = frames_dir / f"f_{best:04d}.png"
    if not p.exists():
        p = frames_dir / f"f_{best:05d}.png"
    im = Image.open(p).convert("RGB").resize((1280, 720), Image.LANCZOS)
    label = _thumb_words(script.get("title_idea") or "", script.get("key_words") or [],
                         (settings.get("_meta") or {}).get("thumb_text", ""))
    ti = fr.fit_text(label, int(1280 * .58), int(720 * .17), fill=fr.palette.highlight(), stroke=fr.OUT, stroke_w=.12)
    im.paste(ti, (int(1280 * .5 - ti.width / 2), int(720 * .14 - ti.height / 2)), ti)
    im.save(out, "JPEG", quality=90)
    return out


def preview_still(script: dict, settings: dict, t: float, out: Path, quality: str = "draft") -> Path:
    """One 3D frame of a script at time t (no voices: timings estimated) — for the dashboard and tests."""
    from ..episode import _size, estimate_audio
    W, H = _size({**settings, "render_scale": .5})
    snd = estimate_audio(script, 24)
    tl = fr.Timeline(script, snd, W, H, 24, settings)
    tl._3d_sets = tuple(set_specs(script))
    st = frame_state(tl, max(0.0, min(t, snd["duration"] - .1)))
    rw, rh, _, samples = QUALITY[quality]
    work = out.parent / (out.stem + "_job")
    work.mkdir(parents=True, exist_ok=True)
    job = {"W": rw, "H": rh, "fps": 24, "out_dir": str(work), "first": 0, "last": 0, "samples": samples, "engine": "auto",
           "outline": True, "cast": cast_specs(script), "sets": set_specs(script),
           "frames": [{k: v for k, v in st.items() if not k.startswith("_")}]}
    run_blender(job, work)
    img = Image.open(work / "f_0000.png").convert("RGB")
    hud(tl, st["t"], img, st).save(out)
    shutil.rmtree(work, ignore_errors=True)
    return out
