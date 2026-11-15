"""Pro-level AI animation on top of the code render (Settings → animation, or per episode).

Modes
  code  the CartoonForge renderer only (free, exact lip-sync, exact counting, flash-safe)
  hero  + AI-animated hero shots: the opening tease, story turning points, the song, the goodbye (4-8 clips)
  full  every shot re-animated by the AI video model

How it keeps the show on-model: every clip is IMAGE-to-video, started from the exact code-rendered frame of that
moment (same characters, colours, set and art style), with a prompt that forbids redesigning anyone. Our own voices,
songs and music stay: the AI clip's audio is dropped and the picture is laid over the episode's timeline. A budget
cap (ai_budget_usd) stops spending; shots past the cap keep the code animation, so a render never fails here.

Providers (researched Nov 2026; check pricing pages before budgeting):
  omni    Google Gemini Omni Flash  gemini-omni-1.2-flash   GEMINI_API_KEY   ~$0.07/s at 720p, 3-15 s clips
          (replaced the Veo 3.1 preview in the Gemini API, which shut down on 22 Oct 2026)
  kling   Kling 4.0 via fal.ai      fal-ai/kling-video/v4/image-to-video  FAL_KEY  ~$0.157/s, 3-30 s, best motion
  runway  Runway Gen-4 Turbo        gen4_turbo              RUNWAY_API_KEY   ~$0.05/s, 5 or 10 s
"""
from __future__ import annotations

import base64
import json
import math
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .. import config
from ..settings import secret

PROVIDERS: dict[str, dict] = {
    "omni": {"label": "Google Gemini Omni Flash", "model": "gemini-omni-1.2-flash", "key": "GEMINI_API_KEY",
             "usd_per_s": 0.07, "min_s": 3, "max_s": 15, "steps": None,
             "best_for": "Best value; uses the Gemini key you already have",
             "note": "Image + text to video, 720p, 3-15 s. Google's current video model in the Gemini API "
                     "(the Veo 3.1 preview there was shut down on 22 Oct 2026)."},
    "kling": {"label": "Kling 4.0 (fal.ai)", "model": "fal-ai/kling-video/v4/image-to-video", "key": "FAL_KEY",
              "usd_per_s": 0.157, "min_s": 3, "max_s": 30, "steps": None,
              "best_for": "Most polished character motion (pro look)",
              "note": "Image-to-video with keyframes, 720p/1080p, 3-30 s. Pay-as-you-go through fal.ai."},
    "runway": {"label": "Runway Gen-4 Turbo", "model": "gen4_turbo", "key": "RUNWAY_API_KEY",
               "usd_per_s": 0.05, "min_s": 5, "max_s": 10, "steps": [5, 10],
               "best_for": "Cheapest per second; fast",
               "note": "Image-to-video, 720p, 5 or 10 s clips. Runway developer API credits."},
}
ORDER = ("omni", "kling", "runway")
MODES = [
    {"id": "code", "label": "Code animation", "note": "Free. Exact lip-sync, counting and flash safety. Characters "
                                                       "never drift."},
    {"id": "hero", "label": "AI hero shots", "note": "Code animation plus 4-8 AI-animated moments (opening, story "
                                                     "turning points, song, goodbye). About $1-5 an episode."},
    {"id": "full", "label": "Full AI animation", "note": "Every shot re-animated by the AI model from the code frame. "
                                                         "Most cinematic; $25-300 an episode; lip-sync is approximate."},
]
STYLE_WORDS = {
    "classic": "soft 3D-shaded picture-book cartoon, warm light",
    "toy3d": "3D animated kids' show, soft vinyl-toy characters, cartoon outlines, warm studio light",
    "paper": "cut-paper stop-motion, layered paper, soft shadows",
    "comic": "bold comic-book animation, ink outlines, halftone",
    "pixel": "16-bit pixel-art animation",
    "anime": "90s cel-animated anime",
    "ps2": "early-2000s 3D game cutscene look",
    "risograph": "two-colour risograph print animation, grain",
}
MOTION = {"wave": "waves happily", "jump": "jumps with joy", "dance": "dances", "point": "points at something",
          "think": "taps their chin, thinking", "clap": "claps", "sleep": "yawns sleepily", "walk": "walks along",
          "stretch": "stretches up high", "idle": "moves gently and naturally"}


def configured() -> list[str]:
    return [p for p in ORDER if secret(PROVIDERS[p]["key"])]


def active(settings: dict) -> str | None:
    want = settings.get("ai_video_provider") or "auto"
    ok = configured()
    if want in ok:
        return want
    return ok[0] if ok else None


def clip_len(provider: str, want: float) -> int:
    p = PROVIDERS[provider]
    if p["steps"]:
        return min(p["steps"], key=lambda s: (s < want, abs(s - want)))
    return int(max(p["min_s"], min(p["max_s"], math.ceil(want))))


def estimate(mode: str, minutes: float, provider: str | None, hero_shots: int = 6) -> dict:
    if mode == "code" or not provider:
        return {"usd": 0.0, "clips": 0, "seconds": 0}
    p = PROVIDERS[provider]
    if mode == "hero":
        n, secs = hero_shots, hero_shots * clip_len(provider, 8)
    else:
        total = minutes * 60 * .97
        avg = 3.2                                       # average shot length at rapid pace (lines are short)
        n = int(total / avg)
        secs = n * clip_len(provider, avg)
    return {"usd": round(secs * p["usd_per_s"], 2), "clips": n, "seconds": int(secs)}


def catalog(settings: dict) -> dict:
    act = active(settings)
    mins = float(settings.get("target_minutes", 12))
    n = int(settings.get("ai_video_hero_shots", 6))
    return {"providers": [{"id": k, **{f: v[f] for f in ("label", "model", "key", "usd_per_s", "best_for", "note")},
                           "clip_s": v["steps"] or [v["min_s"], v["max_s"]], "configured": bool(secret(v["key"]))}
                          for k, v in PROVIDERS.items()],
            "recommended": "omni", "active": act, "modes": MODES,
            "estimate": {m["id"]: estimate(m["id"], mins, act or "omni", n)["usd"] for m in MODES}}


# ---------------------------------------------------------------- shot choice
def pick_shots(script: dict, scenes: list[dict], mode: str, n: int, provider: str) -> list[dict]:
    """[{t, dur, scene}] — non-overlapping moments to animate."""
    segs = script.get("segments") or []
    if mode == "full":
        out = []
        for sc in scenes:
            d = sc["end"] - sc["start"]
            if d >= .8:
                out.append({"t": sc["start"], "dur": d, "scene": sc})
        return out
    pri: list[tuple[int, dict]] = []
    for sc in scenes:
        seg = segs[sc["seg"]] if sc["seg"] < len(segs) else {}
        kind, first = seg.get("kind"), sc["idx"] == 0
        nsc = len(seg.get("scenes") or [])
        if kind == "hello" and first:
            pri.append((0, sc))                                         # the hook: first seconds decide everything
        elif kind == "story" and (first or sc["idx"] == nsc // 2):
            pri.append((1, sc))                                         # story opening + turning point
        elif kind == "song" and sc.get("kind") == "sing" and not any(p[1].get("seg") == sc["seg"] for p in pri):
            pri.append((1, sc))                                         # first sung line
        elif kind in ("explore", "movement") and first:
            pri.append((2, sc))
        elif kind == "goodbye" and sc["idx"] == nsc - 1:
            pri.append((2, sc))
    want = clip_len(provider, 8)
    out: list[dict] = []
    for _, sc in sorted(pri, key=lambda p: (p[0], p[1]["start"])):
        if len(out) >= n:
            break
        if any(abs(sc["start"] - o["t"]) < 15 for o in out):
            continue
        out.append({"t": sc["start"], "dur": float(want), "scene": sc})
    return sorted(out, key=lambda o: o["t"])


def _prompt(script: dict, shot: dict, style: str) -> str:
    from ..kids import cast as castmod
    sc = shot["scene"]
    seg = (script.get("segments") or [{}])[sc["seg"]] if sc["seg"] < len(script.get("segments") or []) else {}
    line = (seg.get("scenes") or [{}])[sc["idx"]] if sc["idx"] < len(seg.get("scenes") or []) else {}
    names = {g["id"]: g.get("name", g["id"]) for g in script.get("characters") or [] if g.get("id")}
    names.update({k: v["name"] for k, v in castmod.CAST.items()})
    who = names.get(line.get("speaker"), "the character")
    act = MOTION.get(line.get("action") or "idle", MOTION["idle"])
    feel = line.get("emotion") or "happy"
    sing = " and sings" if line.get("kind") == "sing" else " and talks"
    return (f"Animate this exact frame from a gentle preschool cartoon. {who} {act}{sing}, feeling {feel}; the other "
            f"characters react warmly. Scene: {seg.get('title', '')} — \"{str(line.get('text', ''))[:160]}\". "
            f"Style: {STYLE_WORDS.get(style, STYLE_WORDS['classic'])}, matching the frame exactly. Keep every "
            "character's design, colours, proportions and outfit EXACTLY as in the frame; do not add or remove "
            "characters; no text, no logos; soft smooth motion, slow gentle camera; bright, calm lighting; no flashing, "
            "nothing scary. No dialogue audio needed.")


# ---------------------------------------------------------------- providers
def _omni(img: bytes, prompt: str, secs: int, out: Path) -> None:
    key = secret("GEMINI_API_KEY")
    body = {"model": PROVIDERS["omni"]["model"],
            "input": [{"type": "image", "data": base64.b64encode(img).decode(), "mime_type": "image/jpeg"},
                      {"type": "text", "text": prompt}],
            "response_format": {"type": "video", "aspect_ratio": "16:9", "resolution": "720p", "duration": f"{secs}s"}}
    r = httpx.post("https://generativelanguage.googleapis.com/v1beta/interactions", json=body, timeout=900,
                   headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    r.raise_for_status()

    def find(o):
        if isinstance(o, dict):
            if o.get("type") == "video" and (o.get("data") or o.get("uri")):
                return o
            for v in o.values():
                f = find(v)
                if f:
                    return f
        elif isinstance(o, list):
            for v in o:
                f = find(v)
                if f:
                    return f
        return None
    v = find(r.json())
    if not v:
        raise RuntimeError("Omni returned no video")
    if v.get("data"):
        out.write_bytes(base64.b64decode(v["data"]))
    else:
        fid = v["uri"].rstrip("/").split("/files/")[-1].split(":")[0]
        _download(f"https://generativelanguage.googleapis.com/v1beta/files/{fid}:download?alt=media", out,
                  {"x-goog-api-key": key})


def _kling(img: bytes, prompt: str, secs: int, out: Path) -> None:
    h = {"Authorization": f"Key {secret('FAL_KEY')}"}
    r = httpx.post(f"https://queue.fal.run/{PROVIDERS['kling']['model']}", headers=h, timeout=60,
                   json={"prompt": prompt, "duration": secs, "resolution": "720p",
                         "start_image_url": "data:image/jpeg;base64," + base64.b64encode(img).decode()})
    r.raise_for_status()
    job = r.json()
    status_url, resp_url = job["status_url"], job["response_url"]
    for _ in range(240):                              # up to ~20 min
        time.sleep(5)
        st = httpx.get(status_url, headers=h, timeout=30).json()
        if st.get("status") == "COMPLETED":
            break
        if st.get("status") in ("FAILED", "ERROR"):
            raise RuntimeError(f"Kling failed: {json.dumps(st)[:200]}")
    else:
        raise TimeoutError("Kling took too long")
    res = httpx.get(resp_url, headers=h, timeout=60).json()
    _download(res["video"]["url"], out)


def _runway(img: bytes, prompt: str, secs: int, out: Path) -> None:
    h = {"Authorization": f"Bearer {secret('RUNWAY_API_KEY')}", "X-Runway-Version": "2024-11-06"}
    base = "https://api.dev.runwayml.com/v1"
    r = httpx.post(f"{base}/image_to_video", headers=h, timeout=60,
                   json={"model": "gen4_turbo", "promptText": prompt[:1000], "ratio": "1280:720", "duration": secs,
                         "promptImage": "data:image/jpeg;base64," + base64.b64encode(img).decode()})
    r.raise_for_status()
    tid = r.json()["id"]
    for _ in range(240):
        time.sleep(5)
        t = httpx.get(f"{base}/tasks/{tid}", headers=h, timeout=30).json()
        if t.get("status") == "SUCCEEDED":
            _download(t["output"][0], out)
            return
        if t.get("status") in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Runway failed: {t.get('failure', '')}"[:200])
    raise TimeoutError("Runway took too long")


CALL = {"omni": _omni, "kling": _kling, "runway": _runway}


def _download(url: str, out: Path, headers: dict | None = None) -> None:
    with httpx.stream("GET", url, headers=headers or {}, timeout=300, follow_redirects=True) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)


# ---------------------------------------------------------------- compose
def _frame(video: Path, t: float, out: Path) -> bytes:
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-ss", f"{t + .05:.3f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=1280:-2", "-q:v", "3", str(out)], check=True)
    return out.read_bytes()


def _enc(W: int, H: int, fps: int) -> list[str]:
    return ["-c:v", "libx264", "-preset", config.X264_PRESET, "-crf", str(config.X264_CRF), "-pix_fmt", "yuv420p",
            "-r", str(fps), "-video_track_timescale", "90000", "-an"]


def compose(base: Path, clips: list[dict], out: Path, W: int, H: int, fps: int, duration: float) -> Path:
    """Lay the AI clips over the base video at their times (picture only; the soundtrack stays ours)."""
    work = out.parent / "aiv_parts"
    work.mkdir(parents=True, exist_ok=True)
    parts, t = [], 0.0
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},setsar=1"
    for i, c in enumerate(sorted(clips, key=lambda c: c["t"])):
        a, b = c["t"], min(duration, c["t"] + c["dur"])
        if a - t > 1 / fps:
            p = work / f"g{i:04d}.mp4"
            subprocess.run([config.FFMPEG, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(base), "-t", f"{a - t:.3f}",
                            *_enc(W, H, fps), str(p)], check=True)
            parts.append(p)
        p = work / f"c{i:04d}.mp4"
        subprocess.run([config.FFMPEG, "-y", "-v", "error", "-i", c["path"], "-t", f"{b - a:.3f}",
                        "-vf", f"{fit},tpad=stop_mode=clone:stop_duration={b - a:.3f}", "-t", f"{b - a:.3f}",
                        *_enc(W, H, fps), str(p)], check=True)
        parts.append(p)
        t = b
    if duration - t > 1 / fps:
        p = work / "tail.mp4"
        subprocess.run([config.FFMPEG, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(base), *_enc(W, H, fps), str(p)],
                       check=True)
        parts.append(p)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(base),
                    "-map", "0:v", "-map", "1:a", "-c", "copy", "-movflags", "+faststart", "-shortest", str(out)],
                   check=True, cwd=work)
    return out


def enhance(script: dict, render_out: dict, settings: dict, workdir: Path, log=print) -> dict:
    """Run the chosen mode on a finished code render. Returns the ai_video report; replaces render_out['video']."""
    mode = settings.get("_animation") or settings.get("animation") or "code"
    if mode not in ("hero", "full"):
        return {"mode": "code"}
    prov = active(settings)
    if not prov:
        log("AI animation skipped: add a GEMINI_API_KEY, FAL_KEY or RUNWAY_API_KEY in Settings → Keys", "warn")
        return {"mode": mode, "provider": None, "clips": [], "usd": 0, "error": "no provider key"}
    budget = float(settings.get("_ai_budget") or settings.get("ai_video_budget_usd") or 5)
    shots = pick_shots(script, render_out.get("scenes") or [], mode, int(settings.get("ai_video_hero_shots", 6)), prov)
    price = PROVIDERS[prov]["usd_per_s"]
    plan, spent = [], 0.0
    for s in shots:
        secs = clip_len(prov, s["dur"])
        cost = secs * price
        if spent + cost > budget:
            plan.append({**s, "secs": secs, "status": "skipped", "usd": 0})
            continue
        spent += cost
        plan.append({**s, "secs": secs, "status": "todo", "usd": round(cost, 3)})
    todo = [p for p in plan if p["status"] == "todo"]
    log(f"AI animation ({mode}, {PROVIDERS[prov]['label']}): {len(todo)} clip(s), ≈${spent:.2f} "
        f"(budget ${budget:.2f}{', ' + str(len(plan) - len(todo)) + ' over budget keep code animation' if len(todo) < len(plan) else ''})")
    style = settings.get("_style") or "classic"
    clip_dir = workdir / "ai_clips"
    clip_dir.mkdir(parents=True, exist_ok=True)

    def one(i_p):
        i, p = i_p
        try:
            img = _frame(Path(render_out["video"]), p["t"], clip_dir / f"k{i:04d}.jpg")
            path = clip_dir / f"clip{i:04d}.mp4"
            CALL[prov](img, _prompt(script, p, style), p["secs"], path)
            p.update(status="ok", path=str(path))
        except Exception as e:  # noqa: BLE001
            p.update(status="failed", error=str(e)[:200], usd=0)
        return p
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, enumerate(todo)))
    ok = [p for p in todo if p["status"] == "ok"]
    if ok:
        out = workdir / "episode_ai.mp4"
        compose(Path(render_out["video"]), [{"t": p["t"], "dur": min(p["dur"], p["secs"]), "path": p["path"]} for p in ok],
                out, render_out["W"], render_out["H"], render_out["fps"], render_out["duration"])
        render_out["video"] = out
    fails = [p for p in todo if p["status"] == "failed"]
    if fails:
        log(f"{len(fails)} AI clip(s) failed and keep the code animation: {fails[0].get('error', '')}", "warn")
    return {"mode": mode, "provider": prov, "model": PROVIDERS[prov]["model"],
            "usd": round(sum(p["usd"] for p in plan if p["status"] == "ok"), 2),
            "clips": [{"t": round(p["t"], 2), "dur": round(min(p["dur"], p["secs"]), 2), "status": p["status"],
                       "usd": p["usd"], **({"error": p["error"]} if p.get("error") else {})} for p in plan]}
