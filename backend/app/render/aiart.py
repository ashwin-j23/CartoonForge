"""AI-illustrated backgrounds (optional, Settings → ai_backgrounds).

Why only backgrounds: an episode is 10-15 minutes and the channel posts several a day; generating all of that
with an AI *video* model would cost roughly $25-$150 per episode and the characters would drift from shot to
shot. Characters therefore stay code-drawn (identical forever, free), while each story place gets a painted
picture-book background from an AI *image* model — about 6-10 images per episode, a few cents each.

Providers (first available key wins, both already used elsewhere in the app):
  Gemini  gemini-2.5-flash-image  (GEMINI_API_KEY; 16:9 output)
  OpenAI  gpt-image-1             (OPENAI_API_KEY; 1536x1024, cropped to 16:9)
Every image is generated once per (episode, set) and kept in the episode's work folder; on any failure the
code-drawn set is used, so a render never fails because of this.
"""
from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

import httpx
from PIL import Image

from ..settings import secret
from .sets import SETS

STYLE_WORDS = {
    "classic": "soft gouache children's picture-book painting, warm light, rounded friendly shapes",
    "paper": "layered cut-paper craft collage, visible paper grain, soft drop shadows",
    "comic": "bold comic-book background, thick ink outlines, halftone shading, flat bright colour",
    "pixel": "16-bit pixel-art game background, limited palette",
    "anime": "90s cel-animated anime background painting, soft pastel sky",
    "ps2": "early-2000s 3D video game scenery, soft textures, light fog",
    "risograph": "two-colour risograph print illustration, pink and blue inks, grain",
}


def _prompt(set_id: str, place: str, style: str) -> str:
    return (f"Background illustration for a preschool TV show: {place or set_id.replace('_', ' ')}. "
            f"Style: {STYLE_WORDS.get(style, STYLE_WORDS['classic'])}. Wide 16:9 landscape, gentle cheerful colours, "
            "simple uncluttered composition, a flat open ground area across the bottom third where characters will "
            "stand, nothing scary. NO people, NO animals, NO characters, NO text, NO letters, NO logos, NO brands.")


def _gemini(prompt: str) -> bytes:
    key = secret("GEMINI_API_KEY")
    r = httpx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent",
                   headers={"x-goog-api-key": key, "Content-Type": "application/json"}, timeout=120,
                   json={"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9"}}})
    r.raise_for_status()
    for c in r.json().get("candidates", []):
        for p in (c.get("content") or {}).get("parts", []):
            data = (p.get("inlineData") or p.get("inline_data") or {}).get("data")
            if data:
                return base64.b64decode(data)
    raise RuntimeError("Gemini returned no image")


def _openai(prompt: str) -> bytes:
    r = httpx.post("https://api.openai.com/v1/images/generations", timeout=180,
                   headers={"Authorization": f"Bearer {secret('OPENAI_API_KEY')}"},
                   json={"model": "gpt-image-1", "prompt": prompt, "size": "1536x1024", "quality": "medium", "n": 1})
    r.raise_for_status()
    return base64.b64decode(r.json()["data"][0]["b64_json"])


def generate(set_id: str, place: str, style: str, out: Path) -> Path | None:
    prompt = _prompt(set_id, place, style)
    for name, fn, key in (("gemini", _gemini, "GEMINI_API_KEY"), ("openai", _openai, "OPENAI_API_KEY")):
        if not secret(key):
            continue
        try:
            raw = fn(prompt)
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            w, h = im.size                                   # centre-crop to 16:9
            th = int(w * 9 / 16)
            if th <= h:
                im = im.crop((0, (h - th) // 2, w, (h - th) // 2 + th))
            else:
                tw = int(h * 16 / 9)
                im = im.crop(((w - tw) // 2, 0, (w - tw) // 2 + tw, h))
            out.parent.mkdir(parents=True, exist_ok=True)
            im.save(out, "JPEG", quality=92)
            return out
        except Exception as e:  # noqa: BLE001
            print(f"[aiart] {name} failed for {set_id}: {str(e)[:160]}")
    return None


def prepare(script: dict, workdir: Path, style: str, log=print) -> dict[str, str]:
    """One illustrated background per distinct set in the episode -> {set_id: image path}."""
    if not (secret("GEMINI_API_KEY") or secret("OPENAI_API_KEY")):
        return {}
    places: dict[str, str] = {}
    for seg in script.get("segments", []):
        sid = seg.get("set") or "meadow"
        if sid not in places:
            places[sid] = f"{seg.get('title', '')} — {SETS.get(sid, {}) and sid.replace('_', ' ')}, " \
                          f"for an episode about {script.get('topic', '')}"
    out = {}
    for sid, place in list(places.items())[:10]:
        h = hashlib.md5((sid + place + style).encode()).hexdigest()[:10]
        p = generate(sid, place, style, workdir / "ai_bg" / f"{sid}-{h}.jpg")
        if p:
            out[sid] = str(p)
    log(f"AI backgrounds: {len(out)}/{len(places)} illustrated")
    return out
