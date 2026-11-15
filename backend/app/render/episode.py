"""Render a whole episode: soundtrack -> frames (in parallel) -> H.264 1080p -> loudness-normalised mux.

15 minutes x 24 fps = 21,600 frames. Frames are split into contiguous chunks, one per CPU; each worker pipes raw
RGB into its own ffmpeg, then the chunks are concatenated losslessly and muxed with the audio.
"""
from __future__ import annotations

import multiprocessing as mp
import pickle
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config
from ..kids import psychology
from . import audio as audiomod
from .characters import sprite
from .common import OUT, fit_text, rounded, text_img
from .frame import Timeline, render as render_frame
from .icons import icon


def _size(settings: dict) -> tuple[int, int]:
    k = float(settings.get("render_scale", 1.0) or 1.0)
    W = int(config.RENDER_WIDTH * k) // 2 * 2
    H = int(config.RENDER_HEIGHT * k) // 2 * 2
    return W, H


def _worker(args):
    tl_path, start, end, out, fps = args
    with open(tl_path, "rb") as f:
        tl: Timeline = pickle.load(f)
    W, H = tl.out_W, tl.out_H          # frames come out at output size (the world is supersampled inside)
    cmd = [config.FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-c:v", "libx264", "-preset", config.X264_PRESET, "-tune", "animation", "-crf", str(config.X264_CRF),
           "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
           "-g", str(fps * 4), "-threads", "2", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    lum = []
    for fi in range(start, end):
        im = render_frame(tl, fi / fps).convert("RGB")
        if fi % 2 == 0:
            lum.append(float(np.asarray(im.resize((32, 18))).mean()))
        p.stdin.write(im.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on frames {start}-{end}")
    return out, lum


def render(script: dict, settings: dict, workdir: Path, log=print, progress=None) -> dict:
    if settings.get("_style") == "toy3d":                 # real 3D picture (Blender), same soundtrack + plan
        from . import three_d
        if three_d.available():
            return three_d.render_video(script, settings, workdir, log, progress)
        log("3D cartoon look needs Blender (backend/tools/blender) — rendering in the classic 2D look instead")
        settings = {**settings, "_style": "classic"}
    workdir.mkdir(parents=True, exist_ok=True)
    W, H = _size(settings)
    fps = config.RENDER_FPS
    wav = workdir / "soundtrack.wav"
    log("Recording voices and music…")
    snd = audiomod.build(script, settings, wav, fps, log)
    if progress:
        progress("rendering", 30)
    tl = Timeline(script, snd, W, H, fps, settings)
    tl_path = workdir / "timeline.pkl"
    with open(tl_path, "wb") as f:
        pickle.dump(tl, f)
    total = int(snd["duration"] * fps)
    n = config.RENDER_WORKERS or config._auto_workers()
    bounds = [round(total * i / n) for i in range(n + 1)]
    jobs = [(str(tl_path), bounds[i], bounds[i + 1], str(workdir / f"part{i:02d}.mp4"), fps) for i in range(n)]
    log(f"Drawing {total} frames ({W}x{H} @ {fps} fps) on {n} worker(s)…")
    parts, lum = [], []
    ctx = mp.get_context("fork")
    with ctx.Pool(n) as pool:
        for k, (out, l) in enumerate(pool.imap(_worker, jobs)):
            parts.append(out)
            lum += l
            if progress:
                progress("rendering", 30 + int(60 * (k + 1) / n))
    lst = workdir / "parts.txt"
    lst.write_text("".join(f"file '{Path(p).name}'\n" for p in parts))
    video = workdir / "episode.mp4"
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(wav),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", "loudnorm=I=-15:TP=-1.5:LRA=11", "-ar", "48000",
                    "-ac", "2", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(video)],
                   check=True, cwd=workdir)
    for p in parts:
        Path(p).unlink(missing_ok=True)
    thumb = workdir / "thumb.jpg"
    thumbnail(script, settings, thumb)
    return {"video": video, "thumb": thumb, "duration": snd["duration"], "segments": snd["segments"],
            "engines": snd["engines"], "flash": flash_check(lum, fps / 2), "W": W, "H": H, "fps": fps,
            "song_regions": snd["song_regions"],
            "scenes": [{k: sc.get(k) for k in ("seg", "idx", "speaker", "start", "end", "kind")} for sc in snd.get("scenes", [])]}


def flash_check(lum: list[float], rate: float) -> dict:
    """Count big luminance swings per second (photosensitivity: >3 flashes/s is the danger zone)."""
    if len(lum) < 3:
        return {"max_per_s": 0}
    swings = [1 if abs(lum[i] - lum[i - 1]) > 40 else 0 for i in range(1, len(lum))]
    win = max(1, int(rate))
    mx = max(sum(swings[i:i + win]) for i in range(0, max(1, len(swings) - win + 1)))
    return {"max_per_s": mx}


# ---------------------------------------------------------------- preview without voices
def estimate_audio(script: dict, fps: int) -> dict:
    """A timeline from word counts (no TTS) so the dashboard can preview any frame of a script instantly."""
    b = psychology.band(script["age_band"])
    t = 4.0
    scenes, segs = [], []
    for si, seg in enumerate(script["segments"]):
        if si:
            t += audiomod.GAP_SEG
        s0 = t
        for ci, sc in enumerate(seg["scenes"]):
            words = sc["text"].split()
            dur = max(1.0, len(words) / b["wpm"] * 60)
            ws = [{"w": w, "s": t + i * dur / len(words), "e": t + (i + 1) * dur / len(words)} for i, w in enumerate(words)]
            end = t + dur + (b["pause"] if sc.get("kind") == "question" else .4)
            scenes.append({"seg": si, "idx": ci, "speaker": sc["speaker"], "start": t, "voice_end": t + dur, "end": end,
                           "kind": sc.get("kind", "line"), "words": ws,
                           "reveal": audiomod._reveal_times(sc.get("card"), ws, t, dur),
                           "sing": sc.get("kind") == "sing" and seg["kind"] == "song"})
            t = end
        segs.append({"title": seg["title"], "kind": seg["kind"], "set": seg.get("set"), "start": s0, "end": t})
    mouth = np.array([.6 if int(i / 3) % 2 else .1 for i in range(int((t + 6) * fps) + 1)], np.float32)
    return {"scenes": scenes, "segments": segs, "mouth": mouth, "duration": t + 6, "jingle": 4.0, "outro_start": t + .3}


def preview(script: dict, settings: dict, t: float, timeline: list | None = None, scale: float = .5) -> Image.Image:
    W, H = _size({**settings, "render_scale": scale})
    snd = estimate_audio(script, 24)
    tl = Timeline(script, snd, W, H, 24, settings)
    return render_frame(tl, max(0.0, min(t, snd["duration"] - .1)))


# ---------------------------------------------------------------- thumbnail
def thumbnail(script: dict, settings: dict, out: Path, size=(1280, 720)) -> Path:
    """Bright, simple, 1-3 big words. Three styles the optimizer A/B tests (settings._thumb):
    face = one big happy character + the object; object = the object huge, character small; duo = two friends."""
    from PIL import ImageEnhance
    from . import sets
    from ..kids import psychology as ps
    from .styles import set_style
    set_style(settings.get("_style") or (settings.get("art_style") if settings.get("art_style") != "auto" else None))
    from . import palette
    palette.set_current(settings.get("_palette") or palette.choose(script.get("category"), script.get("age_band")),
                        script.get("age_band", "preschool"))
    style = settings.get("_thumb") or "face"
    W, H = size
    seg = next((s for s in script["segments"] if s["kind"] not in ("hello", "goodbye")), script["segments"][0])
    bg = sets.background(seg.get("set") or "meadow", W, H, min(ps.pace("rapid")["vivid"],
                                                               palette.vivid_cap(script.get("age_band")))).copy()
    speakers = [sc["speaker"] for s in script["segments"] for sc in s["scenes"] if sc["speaker"] != "sunny"]
    from ..kids.cast import STAR
    lead = STAR if STAR in speakers else (speakers[0] if speakers else STAR)      # the star sells the episode
    second = next((c for c in speakers if c != lead), "mimi")
    obj = next((sc["card"].get("object") for s in script["segments"] for sc in s["scenes"]
                if sc.get("card") and sc["card"].get("object")), None)
    if style == "object" and obj:
        ic = icon(obj, int(H * .7))
        bg.paste(ic, (int(W * .6 - ic.width / 2), int(H * .58 - ic.height / 2)), ic)
        sp = sprite(lead, int(H * .5), 2, "open", "surprised", "point")
        bg.paste(sp, (int(W * .02), int(H * .99 - sp.height)), sp)
    elif style == "duo":
        for cid, x, arms in ((lead, .2, "wave"), (second, .5, "up")):
            sp = sprite(cid, int(H * .68), 2, "open", "excited", arms)
            bg.paste(sp, (int(W * x - sp.width / 2), int(H * .99 - sp.height)), sp)
        if obj:
            ic = icon(obj, int(H * .36))
            bg.paste(ic, (int(W * .8 - ic.width / 2), int(H * .62 - ic.height / 2)), ic)
    else:
        sp = sprite(lead, int(H * .78), 2, "open", "excited", "wave")
        bg.paste(sp, (int(W * .05), int(H * .98 - sp.height)), sp)
        if obj:
            ic = icon(obj, int(H * .42))
            bg.paste(ic, (int(W * .66 - ic.width / 2), int(H * .6 - ic.height / 2)), ic)
    words = (script.get("key_words") or [script.get("title_idea", "")])
    label = _thumb_words(script.get("title_idea") or "", words, (settings.get("_meta") or {}).get("thumb_text", ""))
    ti = fit_text(label, int(W * .58), int(H * .17), fill=palette.highlight(), stroke=OUT, stroke_w=.12)
    tx = W * .5 if style == "duo" else W * .68
    bg.paste(ti, (int(tx - ti.width / 2), int(H * .16 - ti.height / 2)), ti)
    badge = rounded(int(W * .2), int(H * .09), int(H * .045), palette.button(), outline=(255, 255, 255), width=4)
    bt = text_img(f"Ages {psychology.band(script['age_band'])['ages']}", int(H * .05), fill=(255, 255, 255), stroke=None)
    badge.alpha_composite(bt, ((badge.width - bt.width) // 2, (badge.height - bt.height) // 2))
    bg.paste(badge, (int(W * .78), int(H * .86)), badge)
    bg = ImageEnhance.Contrast(bg.convert("RGB")).enhance(1.06)
    bg.save(out, "JPEG", quality=90)
    return out


STOP = {"to", "the", "and", "with", "of", "a", "an", "in", "on", "for", "at", "is", "our", "my", "your"}


def _thumb_words(title: str, keys: list[str], given: str = "") -> str:
    """1-3 big words. Never end on 'to/the/and' (a cut-off phrase looks broken)."""
    if given:
        return given[:22]
    t = re.sub(r"\(.*?\)|\|.*$|[^\w\s'!?-]", "", title).strip()
    words = t.split()[:3]
    while words and words[-1].lower() in STOP:
        words.pop()
    return " ".join(words) if words else (keys[0].title() if keys else "Let's Learn!")


# ---------------------------------------------------------------- Shorts (growth)
def cut_short(video: Path, start: float, end: float, out: Path, title: str) -> Path:
    """Vertical 1080x1920 Short: the 16:9 picture centred over a blurred, zoomed copy of itself."""
    dur = max(10.0, min(58.0, end - start))
    vf = ("[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[bg];"
          "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2-140")
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(video),
                    "-filter_complex", vf, "-c:v", "libx264", "-preset", config.X264_PRESET, "-crf", "21",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)], check=True)
    return out


def compile_videos(videos: list[Path], out: Path) -> Path:
    """Long compilation (watch time): episodes back to back, re-encoded to one stream."""
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in videos))
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    "-movflags", "+faststart", str(out)], check=True)
    return out


def probe_duration(path: Path) -> float:
    r = subprocess.run([config.FFMPEG, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
