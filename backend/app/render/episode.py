"""Render a whole episode: soundtrack -> frames (in parallel) -> H.264 1080p -> loudness-normalised mux.

15 minutes x 24 fps = 21,600 frames. Frames are split into contiguous chunks, one per CPU; each worker pipes raw
RGB into its own ffmpeg, then the chunks are concatenated losslessly and muxed with the audio.
"""
from __future__ import annotations

import math
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
def _sticker(img: Image.Image, px: int) -> Image.Image:
    """A thick white outline + soft drop shadow, like a sticker: the subject pops off any background."""
    from PIL import ImageFilter
    pad = px * 2
    a = Image.new("L", (img.width + pad * 2, img.height + pad * 2), 0)
    a.paste(img.split()[-1], (pad, pad))
    ring = a.filter(ImageFilter.MaxFilter(px * 2 + 1)).filter(ImageFilter.GaussianBlur(1.2))
    out = Image.new("RGBA", a.size, (0, 0, 0, 0))
    shadow = ring.filter(ImageFilter.GaussianBlur(px)).point(lambda v: int(v * .45))
    out.paste((20, 10, 40, 255), (px // 2, px), shadow)
    out.paste((255, 255, 255, 255), (0, 0), ring)
    out.alpha_composite(img.convert("RGBA"), (pad, pad))
    return out


def _burst(W: int, H: int, cx: float, cy: float, base: tuple, rays: int = 14) -> Image.Image:
    """Saturated radial background: bright centre, sunburst rays, darker edges (the subject is the brightest thing)."""
    from PIL import ImageDraw, ImageFilter
    import numpy as np
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.hypot((xx - cx) / W, (yy - cy) / H)
    k = np.clip(1 - d * 1.35, 0, 1)[..., None]
    b = np.array(base, float)
    light = 255 - (255 - b) * .3
    dark = b * .82
    img = Image.fromarray((dark + (light - dark) * k).astype("uint8"), "RGB").convert("RGBA")
    rl = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(rl)
    R = max(W, H) * 1.5
    for i in range(rays):
        a0 = 2 * math.pi * i / rays
        a1 = a0 + math.pi / rays
        dr.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)), (cx + R * math.cos(a1), cy + R * math.sin(a1))], fill=46)
    img.paste((255, 255, 255), (0, 0), rl.filter(ImageFilter.GaussianBlur(3)))
    return img


def thumbnail(script: dict, settings: dict, out: Path, size=(1280, 720)) -> Path:
    """Made to be clicked on a phone in a busy kids' feed (CTR), still honest: what's in the thumbnail is in the video.
    Saturated sunburst background in the episode's palette, BIG sticker-outlined subjects, 1-3 huge words.
    The lead is the character the title names ('Bo Shares a Feast!' shows Bo), else the star.
    Three layouts the optimizer A/B tests (settings._thumb): face = one big character + the object;
    object = the object huge with the character pointing at it; duo = two friends."""
    from PIL import ImageEnhance
    from . import sets
    from ..kids import psychology as ps
    from ..kids.cast import CAST, STAR
    from .styles import set_style
    set_style(settings.get("_style") or (settings.get("art_style") if settings.get("art_style") != "auto" else None))
    from . import palette
    palette.set_current(settings.get("_palette") or palette.choose(script.get("category"), script.get("age_band")),
                        script.get("age_band", "preschool"))
    style = settings.get("_thumb") or "face"
    W, H = size
    meta = settings.get("_meta") or {}
    seg = next((s for s in script["segments"] if s["kind"] not in ("hello", "goodbye")), script["segments"][0])
    speakers = [sc["speaker"] for s in script["segments"] for sc in s["scenes"] if sc["speaker"] != "sunny"]
    title = f"{meta.get('title', '')} {script.get('title_idea', '')}"
    named = [cid for cid, c in CAST.items() if cid != "sunny" and re.search(rf"\b{re.escape(c['name'].split()[0])}\b", title)]
    named.sort(key=lambda cid: title.find(CAST[cid]["name"].split()[0]))
    lead = named[0] if named else (STAR if STAR in speakers else (speakers[0] if speakers else STAR))
    second = next((c for c in named[1:] + speakers if c != lead), "mimi" if lead != "mimi" else "pip")
    from .icons import resolve
    objs = [sc["card"]["object"] for s in script["segments"] for sc in s["scenes"]
            if sc.get("card") and sc["card"].get("object") and resolve(sc["card"]["object"])]   # only ones we can draw
    keys = " ".join(str(k).lower() for k in script.get("key_words") or []) + " " + title.lower()
    obj = next((o for o in objs if o.lower() in keys), objs[0] if objs else None)   # prefer the one the title is about
    if style == "object" and not (obj and obj.lower() in title.lower()):
        style = "face"                      # a huge object only sells the click when the title is about that object

    # background: the episode's set, saturated, under a sunburst centred on the subject
    focus_x = {"object": .62, "duo": .45}.get(style, .38)
    bg = sets.background(seg.get("set") or "meadow", W, H, min(ps.pace("rapid")["vivid"],
                                                               palette.vivid_cap(script.get("age_band")))).copy()
    bg = ImageEnhance.Color(bg.convert("RGB")).enhance(1.45).convert("RGBA")
    bedtime = script.get("category") == "bedtime" or re.search(r"bedtime|goodnight|lullaby|sleep", title.lower())
    # bedtime: night blue, so it sits naturally beside the lullabies and read-alouds that send these viewers
    burst = _burst(W, H, W * focus_x, H * .58, (52, 64, 150) if bedtime else palette.button())
    bg = ImageEnhance.Color(Image.blend(bg, burst, .66).convert("RGB")).enhance(1.35).convert("RGBA")
    border = max(6, H // 90)

    def put(img, cx, bottom=None, cy=None):
        st = _sticker(img, border)
        y = int((bottom - st.height) if bottom is not None else cy - st.height / 2)
        bg.alpha_composite(st, (int(cx - st.width / 2), y))

    if style == "object" and obj:
        put(icon(obj, int(H * .74)), W * .62, cy=H * .6)
        put(sprite(lead, int(H * .7), 2, "open", "surprised", "point"), W * .2, bottom=H * 1.06)
    elif style == "duo":
        put(sprite(second, int(H * .74), 2, "open", "excited", "up"), W * .62, bottom=H * 1.07)
        put(sprite(lead, int(H * .8), 2, "open", "excited", "wave"), W * .3, bottom=H * 1.08)   # head below the words
        if obj:
            put(icon(obj, int(H * .34)), W * .86, cy=H * .62)
    else:
        put(sprite(lead, int(H * .98), 2, "open", "excited", "wave"), W * .3, bottom=H * 1.1)
        if obj:
            put(icon(obj, int(H * .5)), W * .76, cy=H * .62)
    words = (script.get("key_words") or [script.get("title_idea", "")])
    label = _thumb_words(script.get("title_idea") or "", words, meta.get("thumb_text", ""))
    ti = fit_text(label, int(W * .66), int(H * .24), fill=palette.highlight(), stroke=OUT, stroke_w=.14)
    ti.putalpha(ti.split()[-1].point(lambda v: v if v > 40 else 0))   # drop the faint haze: no box on bright backgrounds
    tx = W * .5 if style == "duo" else (W * .62 if style != "object" else W * .55)
    tx = min(max(tx, ti.width / 2 + W * .02), W * .98 - ti.width / 2)
    from PIL import ImageFilter
    pad = border * 4                                   # room for the blur, or the shadow ends in a hard box
    m = Image.new("L", (ti.width + pad * 2, ti.height + pad * 2), 0)
    m.paste(ti.split()[-1].point(lambda v: 255 if v > 60 else 0), (pad, pad))
    sh = Image.new("RGBA", m.size, (20, 10, 40, 0))
    sh.putalpha(m.filter(ImageFilter.GaussianBlur(border)).point(lambda v: int(v * .55)))
    bg.alpha_composite(sh, (int(tx - ti.width / 2 + border // 2 - pad), int(H * .15 - ti.height / 2 + border - pad)))
    bg.alpha_composite(ti, (int(tx - ti.width / 2), int(H * .15 - ti.height / 2)))                      # white fill in letter holes
    badge = rounded(int(W * .17), int(H * .08), int(H * .04), palette.button(), outline=(255, 255, 255), width=4)
    bt = text_img(f"Ages {psychology.band(script['age_band'])['ages']}", int(H * .045), fill=(255, 255, 255), stroke=None)
    badge.alpha_composite(bt, ((badge.width - bt.width) // 2, (badge.height - bt.height) // 2))
    bg.paste(badge, (int(W * .81), int(H * .89)), badge)
    bg = ImageEnhance.Contrast(bg.convert("RGB")).enhance(1.1)
    bg.save(out, "JPEG", quality=92)
    return out


STOP = {"to", "the", "and", "with", "of", "a", "an", "in", "on", "for", "at", "is", "our", "my", "your"}


def _thumb_words(title: str, keys: list[str], given: str = "") -> str:
    """1-3 big words. Never end on 'to/the/and' (a cut-off phrase looks broken)."""
    if given and len(given.split()) <= 3:
        return given[:22]
    title = given or title
    t = re.sub(r"\(.*?\)|\|.*$|[^\w\s'!?-]", "", title).strip()
    words = t.split()[:3]
    while words and words[-1].lower() in STOP:
        words.pop()
    return " ".join(words) if words else (keys[0].title() if keys else "Let's Learn!")


# ---------------------------------------------------------------- Shorts (growth)
def short_caption(text: str, out: Path) -> Path | None:
    """The Short's hook words as a big yellow sticker caption (PNG), two lines at most, 3-5 words."""
    words = re.sub(r"\(.*?\)|\|.*$|#\S+", "", str(text or "")).split()[:4]
    while words and words[-1].lower().strip("&,") in STOP | {"&", ""}:      # never end on 'and the'
        words.pop()
    if not words:
        return None
    lines = [" ".join(words)] if len(words) <= 3 else [" ".join(words[:len(words) // 2 + 1]), " ".join(words[len(words) // 2 + 1:])]
    imgs = [fit_text(ln, 980, 150, 60, fill=(255, 221, 0)) for ln in lines]
    im = Image.new("RGBA", (1080, sum(i.height for i in imgs) + 20 * (len(imgs) - 1)), (0, 0, 0, 0))
    y = 0
    for i in imgs:
        im.alpha_composite(i, ((1080 - i.width) // 2, y))
        y += i.height + 20
    im.save(out)
    return out


def cut_short(video: Path, start: float, end: float, out: Path, title: str) -> Path:
    """Vertical 1080x1920 Short: the 16:9 picture centred over a blurred, zoomed copy of itself, the hook words
    dropping in from the top on frame one (Shorts viewers decide in the first second: motion + words, no fade-in)."""
    dur = max(10.0, min(58.0, end - start))
    cap = short_caption(title, out.with_name("caption.png"))
    vf = ("[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[bg];"
          "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2-140" + ("[v];[v][1:v]overlay=0:'min(150,-h+(150+h)*t/0.35)'"
                                                                    if cap else "") + "[out]")
    ins = ["-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(video)] + (["-loop", "1", "-t", f"{dur:.2f}", "-i", str(cap)] if cap else [])
    subprocess.run([config.FFMPEG, "-y", "-v", "error", *ins,
                    "-filter_complex", vf, "-map", "[out]", "-map", "0:a?", "-c:v", "libx264", "-preset", config.X264_PRESET, "-crf", "21",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)],
                   check=True)
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
