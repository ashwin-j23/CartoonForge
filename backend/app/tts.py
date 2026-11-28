"""Human-sounding narration with word timings (for karaoke captions).

Voice IDs are "engine:voice". Engines, most human first:

  elevenlabs:<id>   ElevenLabs multilingual v2 (free 10k chars/month, then paid). Native word timings.
  openai:<voice>    OpenAI gpt-4o-mini-tts, steerable delivery ("excited", "deadpan"...).
  gemini:<voice>    Gemini 2.5 Flash TTS (free tier, low daily limit), steerable delivery.
  chatterbox:<id>   Chatterbox Turbo (MIT, open-source), runs locally on the worker in its own Python environment.
                    "default" = its built-in voice; any other id = a voice sample the owner uploaded WITH the
                    speaker's permission (zero-shot cloning, no training). Outputs carry Chatterbox's watermark.
  kokoro:<voice>    Kokoro-82M, open-source, runs locally on the worker. FREE + UNLIMITED.
                    Default: near-human quality without any key or quota.
  edge:<voice>      Microsoft Edge neural voices (free, online, good).
  espeak:<lang>     Offline robot voice. Last resort only, so a render never fails.

If the chosen voice fails (no key, quota, network), the next engine takes over with a
voice of the same language and gender.
"""
from __future__ import annotations

import asyncio
import base64
import ctypes
import os
import random
import re
import subprocess
import tempfile
import threading
from pathlib import Path

import httpx
import numpy as np

from . import config

os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")      # no onnxruntime telemetry (must precede its import)


def _no_ort_telemetry() -> None:
    """Belt and braces: also switch telemetry off through the API before any InferenceSession is created."""
    try:
        import onnxruntime
        onnxruntime.disable_telemetry_events()
    except Exception:          # older/newer builds without the call, or onnxruntime missing: nothing to disable
        pass

SR = 44100

# ---------------------------------------------------------------- voice catalog
def _v(id, label, gender, lang="en", note=""):
    return {"id": id, "engine": id.split(":")[0], "label": label, "gender": gender, "lang": lang, "note": note}


VOICES = [
    # Kokoro — free, unlimited, very natural. Samples for these ship with the dashboard.
    _v("kokoro:am_michael", "Michael — warm storyteller (US)", "m"),
    # Blends: two Kokoro voices mixed into one new, unique voice (nobody else's channel sounds like it).
    _v("kokoro:am_michael*0.65+am_fenrir*0.35", "Marcus — warm with depth (blend)", "m", note="blend"),
    _v("kokoro:am_michael*0.6+am_puck*0.4", "Leo — friendly, lively (blend)", "m", note="blend"),
    _v("kokoro:af_heart*0.6+af_bella*0.4", "Maya — bright and warm (blend)", "f", note="blend"),
    _v("kokoro:af_heart*0.65+af_nicole*0.35", "Iris — soft, close-mic (blend)", "f", note="blend"),
    _v("kokoro:bm_george*0.6+bm_fable*0.4", "Arthur — British storyteller (blend)", "m", note="blend"),
    _v("chatterbox:default", "Chatterbox — most human, built-in voice (local, slower)", "f"),
    _v("kokoro:af_heart", "Heart — friendly, expressive (US)", "f"),
    _v("kokoro:am_puck", "Puck — playful, upbeat (US)", "m"),
    _v("kokoro:af_bella", "Bella — bright, energetic (US)", "f"),
    _v("kokoro:am_fenrir", "Fenrir — deep, dramatic (US)", "m"),
    _v("kokoro:af_nicole", "Nicole — soft, close-mic (US)", "f"),
    _v("kokoro:am_eric", "Eric — calm, documentary (US)", "m"),
    _v("kokoro:af_sarah", "Sarah — clear, casual (US)", "f"),
    _v("kokoro:bm_george", "George — British, authoritative", "m"),
    _v("kokoro:bf_emma", "Emma — British, polished", "f"),
    _v("kokoro:bm_fable", "Fable — British, storyteller", "m"),
    _v("kokoro:hm_omega", "Omega — Hindi", "m", "hi"),
    _v("kokoro:hf_alpha", "Alpha — Hindi", "f", "hi"),
    _v("kokoro:em_alex", "Alex — Spanish", "m", "es"),
    # ElevenLabs — the most human; needs ELEVENLABS_API_KEY. Any voice ID from your library works too.
    _v("elevenlabs:JBFqnCBsd6RMkjVDRZzb", "George — warm narrator", "m", note="key"),
    _v("elevenlabs:nPczCjzI2devNBz1zQrb", "Brian — deep, resonant", "m", note="key"),
    _v("elevenlabs:TX3LPaxmHKxFdv7VOQHJ", "Liam — young, energetic", "m", note="key"),
    _v("elevenlabs:EXAVITQu4vr4xnSDxMaL", "Sarah — soft, confident", "f", note="key"),
    _v("elevenlabs:XB0fDUnXU5powFXDhCwa", "Charlotte — playful", "f", note="key"),
    _v("elevenlabs:21m00Tcm4TlvDq8ikWAM", "Rachel — calm, clear", "f", note="key"),
    # OpenAI — needs OPENAI_API_KEY; delivery follows the video's mood.
    _v("openai:ash", "Ash — confident male", "m", note="key"),
    _v("openai:onyx", "Onyx — deep male", "m", note="key"),
    _v("openai:ballad", "Ballad — expressive male", "m", note="key"),
    _v("openai:coral", "Coral — warm female", "f", note="key"),
    _v("openai:nova", "Nova — bright female", "f", note="key"),
    _v("openai:sage", "Sage — calm female", "f", note="key"),
    # Gemini — uses GEMINI_API_KEY; free tier has a small daily limit.
    _v("gemini:Puck", "Puck — upbeat male", "m", note="key"),
    _v("gemini:Charon", "Charon — informative male", "m", note="key"),
    _v("gemini:Fenrir", "Fenrir — excitable male", "m", note="key"),
    _v("gemini:Kore", "Kore — firm female", "f", note="key"),
    _v("gemini:Aoede", "Aoede — breezy female", "f", note="key"),
    _v("gemini:Leda", "Leda — youthful female", "f", note="key"),
    # VoxCPM2 — open model, you host it on a GPU (set VOXCPM_URL). Voice designed from a description.
    _v("voxcpm:warm-male", "Warm male (designed)", "m", note="server"),
    _v("voxcpm:bright-female", "Bright female (designed)", "f", note="server"),
    _v("voxcpm:deep-narrator", "Deep narrator (designed)", "m", note="server"),
    _v("voxcpm:indian-english", "Indian English male (designed)", "m", note="server"),
    # Edge — free online neural voices.
    _v("edge:en-US-AndrewMultilingualNeural", "Andrew — warm, confident (US)", "m"),
    _v("edge:en-US-AvaMultilingualNeural", "Ava — bright, expressive (US)", "f"),
    _v("edge:en-US-BrianMultilingualNeural", "Brian — casual (US)", "m"),
    _v("edge:en-US-EmmaMultilingualNeural", "Emma — friendly (US)", "f"),
    _v("edge:en-GB-RyanNeural", "Ryan — British", "m"),
    _v("edge:en-IN-PrabhatNeural", "Prabhat — Indian English", "m"),
    _v("edge:en-IN-NeerjaExpressiveNeural", "Neerja — Indian English", "f"),
    _v("edge:hi-IN-MadhurNeural", "Madhur — Hindi", "m", "hi"),
    _v("edge:hi-IN-SwaraNeural", "Swara — Hindi", "f", "hi"),
    _v("edge:ta-IN-ValluvarNeural", "Valluvar — Tamil", "m", "ta"),
    _v("edge:ta-IN-PallaviNeural", "Pallavi — Tamil", "f", "ta"),
    _v("edge:es-MX-JorgeNeural", "Jorge — Spanish (MX)", "m", "es"),
    # ---- voices used by the kids cast and the language editions
    _v("kokoro:af_sky", "Sky — light, youthful (US)", "f"),
    _v("kokoro:af_nova", "Nova — bright, clear (US)", "f"),
    _v("kokoro:bf_isabella", "Isabella — British, gentle", "f"),
    _v("kokoro:bm_lewis", "Lewis — British, deep and kind", "m"),
    _v("kokoro:af_heart*0.5+af_sky*0.5", "Sunny — warm kids host (blend)", "f", note="blend"),
    _v("kokoro:am_puck*0.7+am_echo*0.3", "Pip — cheeky little buddy (blend)", "m", note="blend"),
    _v("kokoro:ef_dora", "Dora — Spanish", "f", "es"),
    _v("kokoro:ff_siwis", "Siwis — French", "f", "fr"),
    _v("kokoro:if_sara", "Sara — Italian", "f", "it"),
    _v("kokoro:pf_dora", "Dora — Portuguese (BR)", "f", "pt"),
    _v("kokoro:pm_alex", "Alex — Portuguese (BR)", "m", "pt"),
    _v("kokoro:jf_alpha", "Alpha — Japanese", "f", "ja"),
    _v("kokoro:zf_xiaobei", "Xiaobei — Mandarin", "f", "zh"),
    _v("edge:ar-SA-ZariyahNeural", "Zariyah — Arabic", "f", "ar"),
    _v("edge:ar-SA-HamedNeural", "Hamed — Arabic", "m", "ar"),
    _v("edge:id-ID-GadisNeural", "Gadis — Indonesian", "f", "id"),
    _v("edge:id-ID-ArdiNeural", "Ardi — Indonesian", "m", "id"),
    _v("edge:de-DE-KatjaNeural", "Katja — German", "f", "de"),
    _v("edge:de-DE-ConradNeural", "Conrad — German", "m", "de"),
    _v("edge:ru-RU-SvetlanaNeural", "Svetlana — Russian", "f", "ru"),
    _v("edge:ru-RU-DmitryNeural", "Dmitry — Russian", "m", "ru"),
    _v("edge:ko-KR-SunHiNeural", "SunHi — Korean", "f", "ko"),
    _v("edge:ko-KR-InJoonNeural", "InJoon — Korean", "m", "ko"),
    _v("edge:fr-FR-DeniseNeural", "Denise — French", "f", "fr"),
    _v("edge:fr-FR-HenriNeural", "Henri — French", "m", "fr"),
    _v("edge:es-ES-ElviraNeural", "Elvira — Spanish (ES)", "f", "es"),
    _v("edge:pt-BR-FranciscaNeural", "Francisca — Portuguese (BR)", "f", "pt"),
    _v("edge:pt-BR-AntonioNeural", "Antonio — Portuguese (BR)", "m", "pt"),
    _v("edge:ja-JP-NanamiNeural", "Nanami — Japanese", "f", "ja"),
    _v("edge:ja-JP-KeitaNeural", "Keita — Japanese", "m", "ja"),
    _v("edge:zh-CN-XiaoxiaoNeural", "Xiaoxiao — Mandarin", "f", "zh"),
    _v("edge:zh-CN-YunxiNeural", "Yunxi — Mandarin", "m", "zh"),
    _v("edge:it-IT-ElsaNeural", "Elsa — Italian", "f", "it"),
    _v("edge:tr-TR-EmelNeural", "Emel — Turkish", "f", "tr"),
    _v("edge:tr-TR-AhmetNeural", "Ahmet — Turkish", "m", "tr"),
    _v("edge:bn-IN-TanishaaNeural", "Tanishaa — Bengali", "f", "bn"),
    _v("edge:bn-IN-BashkarNeural", "Bashkar — Bengali", "m", "bn"),
    _v("edge:sw-KE-ZuriNeural", "Zuri — Swahili", "f", "sw"),
    _v("edge:sw-KE-RafikiNeural", "Rafiki — Swahili", "m", "sw"),
    _v("edge:vi-VN-HoaiMyNeural", "HoaiMy — Vietnamese", "f", "vi"),
    _v("edge:vi-VN-NamMinhNeural", "NamMinh — Vietnamese", "m", "vi"),
    _v("edge:fil-PH-BlessicaNeural", "Blessica — Filipino", "f", "fil"),
    _v("edge:fil-PH-AngeloNeural", "Angelo — Filipino", "m", "fil"),
    _v("edge:ur-PK-UzmaNeural", "Uzma — Urdu", "f", "ur"),
    _v("edge:ur-PK-AsadNeural", "Asad — Urdu", "m", "ur"),
    _v("edge:th-TH-PremwadeeNeural", "Premwadee — Thai", "f", "th"),
    _v("edge:th-TH-NiwatNeural", "Niwat — Thai", "m", "th"),
]
_BY_ID = {v["id"]: v for v in VOICES}
SAMPLE_DIR = config.FRONTEND_DIST / "voices"

# How each mood should *sound* (used by steerable engines and to tune pacing).
DELIVERY = {
    "energetic": "Upbeat, confident short-form video narrator talking to a friend. Natural, conversational, "
                 "smile in the voice, punch the key words, quick but never rushed. Not an announcer.",
    "funny": "Playful and casual, like telling a funny story to friends. Light comedic timing, small pauses "
             "before punchlines, genuinely amused.",
    "chill": "Relaxed, warm and intimate, like a late-night conversation. Unhurried, soft smile.",
    "mysterious": "Low, curious and slightly hushed, building intrigue. Let suspense breathe with short pauses.",
    "dramatic": "Cinematic documentary narrator. Grounded, serious, with weight on the big reveals.",
    # ---- children's programming
    "playful": "Warm, playful children's TV host talking to a 4-year-old. Big smile in the voice, bouncy and kind, "
               "clear consonants, gentle emphasis on the key word. Never shouty, never babyish.",
    "story": "Cosy picture-book storyteller reading aloud to a small group of children. Expressive, warm, "
             "unhurried; small pauses so little listeners can picture each moment.",
    "bedtime": "Soft, slow, soothing bedtime voice. Calm and low, almost a whisper at the end of lines.",
    "teacher": "Patient, encouraging preschool teacher. Clear and slow on new words, delighted praise.",
    "excited": "Joyful and amazed, like discovering something wonderful with a child. Bright but kind.",
}


MATCH, CLOSE = 0.80, 0.72     # voice-check thresholds (same person ≈ 0.85-0.9, different people ≈ 0.5-0.6)


def all_custom_voices() -> list[dict]:
    try:
        from .settings import app_settings
        return [v for v in app_settings().get("custom_voices") or [] if v.get("consent")]
    except Exception:  # noqa: BLE001
        return []


def custom_voices() -> list[dict]:
    """Uploaded voices that passed the check (or that the owner approved after listening when it was close)."""
    return [v for v in all_custom_voices() if v.get("status") == "ready" or (v.get("status") == "close" and v.get("approved"))]


def samples_of(c: dict) -> list[dict]:
    return c.get("samples") or ([{"url": c["url"], "ext": c.get("ext", "wav")}] if c.get("url") else [])


def _custom_entry(c: dict) -> dict:
    return {**_v(f"chatterbox:{c['id']}", f"{c['name']} — your voice sample (Chatterbox, local)", c.get("gender", "f")),
            "fallback": c.get("fallback") or "edge:en-IN-NeerjaExpressiveNeural"}


def voice_info(vid: str) -> dict:
    if ":" not in vid:  # legacy plain Edge IDs
        vid = "edge:" + vid
    if vid.startswith("chatterbox:") and vid not in _BY_ID:
        c = next((c for c in custom_voices() if f"chatterbox:{c['id']}" == vid), None)
        if c:
            return _custom_entry(c)
    return _BY_ID.get(vid) or {"id": vid, "engine": vid.split(":")[0], "label": vid, "gender": "m", "lang": "en"}


def sample_name(vid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", vid.replace(":", "_")).strip("_")


def catalog() -> list[dict]:
    out = [{**_custom_entry(c), "sample": None, "custom": True} for c in custom_voices()]
    for v in VOICES:
        sample = SAMPLE_DIR / (sample_name(v["id"]) + ".mp3")
        out.append({**v, "sample": f"/voices/{sample.name}" if sample.exists() else None})
    return out


def _secret(name: str) -> str:
    from .settings import secret
    return secret(name)


# ---------------------------------------------------------------- audio helpers
def decode_to_array(path: str) -> np.ndarray:
    raw = subprocess.run([config.FFMPEG, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def decode_bytes(data: bytes, suffix: str, extra_in: list[str] | None = None) -> np.ndarray:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        p = f.name
    try:
        if extra_in:  # raw PCM
            raw = subprocess.run([config.FFMPEG, "-v", "error", *extra_in, "-i", p, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                                 capture_output=True, check=True).stdout
            return np.frombuffer(raw, dtype=np.float32).copy()
        return decode_to_array(p)
    finally:
        os.unlink(p)


def resample(a: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return a.astype(np.float32)
    x = np.linspace(0, len(a), int(len(a) * SR / sr), endpoint=False)
    return np.interp(x, np.arange(len(a)), a).astype(np.float32)


def rate_to_speed(rate: str) -> float:
    try:
        return 1 + int(re.sub(r"[^\d-]", "", rate or "0") or 0) / 100
    except ValueError:
        return 1.0


# ---------------------------------------------------------------- word timing estimation
def _weight(w: str) -> float:
    core = re.sub(r"[^\w']", "", w.lower())
    if not core:
        return 0.3
    if core.isdigit():
        return 0.9 * len(core)
    syl = len(re.findall(r"[aeiouy]+", core)) or 1
    return syl + 0.08 * len(core)


def align_words(text: str, audio: np.ndarray, sr: int = SR) -> list[dict]:
    """Estimate word timings for engines that don't return them.

    Phrase boundaries (punctuation) are snapped to real pauses found in the audio, then
    words are spread inside each phrase by syllable weight. Captions show 2-3 words at a
    time, so this lands within a frame or two of the true timing.
    """
    words = text.split()
    if not words or len(audio) == 0:
        return []
    hop = int(0.01 * sr)
    n = len(audio) // hop
    rms = np.sqrt(np.mean(audio[: n * hop].reshape(n, hop) ** 2, axis=1)) if n else np.zeros(1)
    thr = max(1e-4, 0.12 * float(np.percentile(rms, 95)))
    voiced = np.where(rms > thr)[0]
    if len(voiced) == 0:
        return []
    start, end = float(voiced[0]) * 0.01, float(voiced[-1] + 1) * 0.01
    # silent runs >= 90ms inside speech
    sil, run = [], None
    for i in range(voiced[0], voiced[-1] + 1):
        if rms[i] <= thr:
            run = i if run is None else run
        elif run is not None:
            if i - run >= 9:
                sil.append((run * 0.01, float(i) * 0.01))
            run = None
    weights = [_weight(w) for w in words]
    breaks = [k for k, w in enumerate(words[:-1]) if re.search(r"[.!?,;:…—-]$|\.\.\.$", w)]
    total = sum(weights)
    cum = np.cumsum(weights)
    # snap each phrase break to the nearest unused silence after the previous one
    bounds = []  # (word_index_end, t_end_of_phrase, t_start_of_next)
    last_t = start
    used = set()
    for k in breaks:
        expect = start + (end - start) * float(cum[k]) / total
        best, bd = None, 0.6
        for j, (s0, s1) in enumerate(sil):
            if j in used or s0 < last_t:
                continue
            d = abs((s0 + s1) / 2 - expect)
            if d < bd:
                best, bd = j, d
        if best is not None:
            used.add(best)
            s0, s1 = sil[best]
            bounds.append((k, s0, s1))
            last_t = s1
    out = []
    seg_start_idx, seg_t0 = 0, start
    for k, t_end, t_next in bounds + [(len(words) - 1, end, end)]:
        idx = range(seg_start_idx, k + 1)
        wsum = sum(weights[i] for i in idx) or 1
        t = seg_t0
        dur = max(0.05, t_end - seg_t0)
        for i in idx:
            d = dur * weights[i] / wsum
            out.append({"w": words[i], "s": round(t, 3), "e": round(t + d * 0.92, 3)})
            t += d
        seg_start_idx, seg_t0 = k + 1, t_next
    return out


# ---------------------------------------------------------------- engines
_kokoro = {"lock": threading.Lock(), "model": None}
KOKORO_LANG = {"a": "en-us", "b": "en-gb", "h": "hi", "e": "es", "f": "fr-fr", "i": "it", "p": "pt-br", "j": "ja", "z": "cmn"}
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"


def kokoro_enabled() -> bool:
    return os.getenv("KOKORO_ENABLED", "1") != "0"


def _kokoro_model():
    with _kokoro["lock"]:
        if _kokoro["model"] is None:
            _no_ort_telemetry()
            from kokoro_onnx import Kokoro
            d = Path(os.getenv("KOKORO_DIR", config.DATA_DIR / "models"))
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            model = "kokoro-v1.0.int8.onnx" if os.getenv("KOKORO_INT8") == "1" else "kokoro-v1.0.onnx"
            for name in (model, "voices-v1.0.bin"):
                p = d / name
                if not p.exists() or p.stat().st_size < 1_000_000:
                    tmp = p.with_suffix(".part")
                    with httpx.stream("GET", KOKORO_URL + name, follow_redirects=True, timeout=600) as r:
                        r.raise_for_status()
                        with open(tmp, "wb") as f:
                            for chunk in r.iter_bytes(1 << 20):
                                f.write(chunk)
                    tmp.rename(p)
            _kokoro["model"] = Kokoro(str(d / model), str(d / "voices-v1.0.bin"))
        return _kokoro["model"]


def _kokoro_style(k, voice: str):
    """'am_michael' or a blend like 'am_michael*0.65+am_fenrir*0.35' -> style vector."""
    if "+" not in voice and "*" not in voice:
        return voice
    parts = []
    for term in voice.split("+"):
        name, _, w = term.partition("*")
        parts.append((name.strip(), float(w or 1)))
    total = sum(w for _, w in parts) or 1
    return sum(k.get_voice_style(n) * (w / total) for n, w in parts).astype(np.float32)


def _seed(text: str) -> random.Random:
    import hashlib
    return random.Random(int(hashlib.md5(text.encode()).hexdigest()[:8], 16))


def speech_speed(text: str, base: float, mood: str) -> float:
    """People don't read every line at one speed: punchlines slow down, long setups speed up."""
    words = len(text.split())
    f = {"chill": 0.96, "mysterious": 0.95, "dramatic": 0.97, "story": 0.95, "bedtime": 0.86,
         "teacher": 0.93, "playful": 0.98, "excited": 1.0}.get(mood, 1.0)
    if words <= 5:
        f *= 0.94                     # short punchy line: land it
    elif words >= 20:
        f *= 1.03                     # long setup: keep it moving
    if text.rstrip().endswith("?"):
        f *= 0.98
    f *= 1 + _seed(text).uniform(-0.025, 0.025)   # deterministic per line, so re-renders match
    return max(0.7, min(1.4, base * f))


def _kokoro_tts(text, voice, rate, mood):
    if not kokoro_enabled():
        raise RuntimeError("Kokoro disabled on this instance")
    k = _kokoro_model()
    first = voice.split("+")[0].split("*")[0]
    lang = KOKORO_LANG.get(first[:1], "en-us")
    rnd = _seed(text + voice)
    style = _kokoro_style(k, voice)
    kw = dict(voice=style, speed=speech_speed(text, rate_to_speed(rate), mood), lang=lang,
              sentence_pause=rnd.uniform(0.2, 0.3) + (0.06 if mood in ("mysterious", "dramatic") else 0),
              clause_pause=rnd.uniform(0.08, 0.13))
    multi = len(re.findall(r"[.!?]", text.strip()[:-1])) >= 1
    a = None
    if multi and _kokoro.get("continuous", True):
        try:   # continuous keeps the intonation flowing across sentence joins (needs a duration-export model)
            a, sr = k.create(text, continuous=True, **kw)
        except Exception:
            _kokoro["continuous"] = False
    if a is None:
        try:
            a, sr = k.create(text, **kw)
        except TypeError:          # older kokoro-onnx (<0.5) has no pause controls
            a, sr = k.create(text, voice=kw["voice"], speed=kw["speed"], lang=kw["lang"])
    audio = resample(np.asarray(a, dtype=np.float32), sr)
    return audio, None


def _edge_tts(text, voice, rate, mood):
    import edge_tts

    async def run():
        kw = {"rate": rate, "boundary": "WordBoundary"}
        proxy = os.getenv("TTS_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        if proxy:                                  # aiohttp ignores the proxy settings unless given one
            kw["proxy"] = proxy
        com = edge_tts.Communicate(text, voice, **kw)
        audio, words = bytearray(), []
        async for ch in com.stream():
            if ch["type"] == "audio":
                audio += ch["data"]
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append({"w": ch["text"], "s": s, "e": s + ch["duration"] / 1e7})
        return bytes(audio), words

    audio, words = asyncio.run(run())
    if not audio:
        raise RuntimeError("edge-tts returned no audio")
    return decode_bytes(audio, ".mp3"), words


def _elevenlabs_tts(text, voice, rate, mood):
    key = _secret("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("no ELEVENLABS_API_KEY")
    style = {"funny": 0.45, "energetic": 0.35, "dramatic": 0.4}.get(mood, 0.2)
    r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
                   params={"output_format": "mp3_44100_128"}, timeout=120,
                   headers={"xi-api-key": key, "Content-Type": "application/json"},
                   json={"text": text, "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
                         "voice_settings": {"stability": 0.42, "similarity_boost": 0.8, "style": style,
                                            "use_speaker_boost": True,
                                            "speed": max(0.8, min(1.15, rate_to_speed(rate)))}})
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:160]}")
    data = r.json()
    audio = decode_bytes(base64.b64decode(data["audio_base64"]), ".mp3")
    al = data.get("alignment") or {}
    words, cur, s0, e0 = [], "", None, None
    for ch, s, e in zip(al.get("characters", []), al.get("character_start_times_seconds", []),
                        al.get("character_end_times_seconds", [])):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": s0, "e": e0})
            cur, s0 = "", None
        else:
            cur += ch
            s0 = s if s0 is None else s0
            e0 = e
    if cur:
        words.append({"w": cur, "s": s0, "e": e0})
    return audio, words or None


def _openai_tts(text, voice, rate, mood):
    key = _secret("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("no OPENAI_API_KEY")
    pace = "Slightly faster than normal speech." if rate_to_speed(rate) > 1.05 else ""
    r = httpx.post("https://api.openai.com/v1/audio/speech", timeout=120,
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"), "voice": voice, "input": text,
                         "instructions": DELIVERY.get(mood, DELIVERY["energetic"]) + " " + pace,
                         "response_format": "mp3"})
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI TTS {r.status_code}: {r.text[:160]}")
    return decode_bytes(r.content, ".mp3"), None


def _gemini_tts(text, voice, rate, mood):
    key = _secret("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no GEMINI_API_KEY")
    model = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    style = DELIVERY.get(mood, DELIVERY["energetic"])
    r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                   params={"key": key}, timeout=120,
                   json={"contents": [{"parts": [{"text": f"Read aloud in this style: {style}\n\n{text}"}]}],
                         "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                             "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}})
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini TTS {r.status_code}: {r.text[:160]}")
    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    return resample(audio, 24000), None


# ---- eSpeak NG (offline, last resort)
_es_lock = threading.Lock()
_es: dict = {}


class _EspeakEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("unique_identifier", ctypes.c_uint), ("text_position", ctypes.c_int),
                ("length", ctypes.c_int), ("audio_position", ctypes.c_int), ("sample", ctypes.c_int),
                ("user_data", ctypes.c_void_p), ("id", ctypes.c_char * 8)]


def _espeak_tts(text, voice, rate, mood, female=False):
    import espeakng_loader as L

    with _es_lock:
        if "lib" not in _es:
            lib = ctypes.CDLL(L.get_library_path())
            data = L.get_data_path()
            sr = lib.espeak_Initialize(2, 0, str(Path(data).parent).encode(), 0)
            if sr <= 0:
                sr = lib.espeak_Initialize(2, 0, data.encode(), 0)
            CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int,
                                  ctypes.POINTER(_EspeakEvent))
            state = {"pcm": []}

            def cb(wav, n, ev):
                if n > 0:
                    state["pcm"].append(np.ctypeslib.as_array(wav, shape=(n,)).copy())
                return 0
            cbf = CB(cb)
            lib.espeak_SetSynthCallback(cbf)
            _es.update(lib=lib, sr=sr, cb=cbf, state=state)
        lib, sr, state = _es["lib"], _es["sr"], _es["state"]
        lib.espeak_SetVoiceByName(((voice or "en-us") + ("+f3" if female else "+m3")).encode())
        lib.espeak_SetParameter(1, int(175 * rate_to_speed(rate)), 0)
        state["pcm"].clear()
        b = text.encode("utf-8")
        lib.espeak_Synth(b, len(b) + 1, 0, 1, 0, 1, None, None)
        lib.espeak_Synchronize()
        pcm = np.concatenate(state["pcm"]) if state["pcm"] else np.zeros(1, np.int16)
    return resample(pcm.astype(np.float32) / 32768.0, sr), None


# VoxCPM2 (OpenBMB, Apache-2.0): 2B open model, 48 kHz, "voice design" from a text description.
# It needs a GPU, so it runs as a server you host (vLLM-Omni: `vllm serve openbmb/VoxCPM2 --omni`,
# or any OpenAI-compatible /v1/audio/speech endpoint) and Reelsmith calls it: set VOXCPM_URL.
VOXCPM_DESIGNS = {
    "warm-male": "A warm, confident young man, conversational, a slight smile, natural pauses",
    "bright-female": "A bright, friendly young woman, upbeat and expressive, casual",
    "deep-narrator": "A deep, calm male documentary narrator, grounded and clear",
    "indian-english": "A friendly Indian English male voice, energetic and clear",
}
MOOD_HINT = {"funny": "playful, amused", "mysterious": "hushed, curious", "dramatic": "serious, weighty",
             "chill": "relaxed, warm", "energetic": "lively, punchy"}


def _voxcpm_tts(text, voice, rate, mood):
    base = (_secret("VOXCPM_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("no VOXCPM_URL")
    design = VOXCPM_DESIGNS.get(voice, voice.replace("-", " "))
    pace = ", slightly fast" if rate_to_speed(rate) > 1.04 else ""
    headers = {"Authorization": f"Bearer {_secret('VOXCPM_API_KEY')}"} if _secret("VOXCPM_API_KEY") else {}
    r = httpx.post(f"{base}/audio/speech", timeout=180, headers=headers,
                   json={"model": os.getenv("VOXCPM_MODEL", "openbmb/VoxCPM2"), "voice": "default",
                         "input": f"({design}, {MOOD_HINT.get(mood, 'natural')}{pace}){text}",
                         "response_format": "wav"})
    if r.status_code >= 400:
        raise RuntimeError(f"VoxCPM {r.status_code}: {r.text[:160]}")
    return decode_bytes(r.content, ".wav"), None


# ---- Chatterbox (local, separate Python environment) ------------------------------------------------
_cb = {"lock": threading.Lock(), "proc": None, "refs": {}}
CB_SERVER = Path(__file__).resolve().parent.parent / "voicebox" / "chatterbox_server.py"


def chatterbox_python() -> str:
    """The Python of the Chatterbox environment (worker.yml / Dockerfile install it); '' when not installed."""
    py = os.getenv("CHATTERBOX_PY", "")
    return py if py and Path(py).exists() else ""


def _cb_proc():
    p = _cb["proc"]
    if p and p.poll() is None:
        return p
    py = chatterbox_python()
    if not py:
        raise RuntimeError("Chatterbox is not installed on this machine (CHATTERBOX_PY)")
    p = subprocess.Popen([py, str(CB_SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    first = p.stdout.readline()                       # {"ready": true} once the model is loaded
    if '"ready"' not in first:
        p.kill()
        raise RuntimeError("Chatterbox failed to start")
    _cb["proc"] = p
    return p


def level(a: np.ndarray) -> np.ndarray:
    """Even out a recording: speech RMS to about -20 dBFS, peaks kept under -1 dBFS."""
    rms = float(np.sqrt(np.mean(a ** 2))) or 1e-4
    a = a * (0.1 / rms)
    peak = float(np.max(np.abs(a))) or 1.0
    return (a * min(1.0, 0.89 / peak)).astype(np.float32)


def sample_wav(url: str, ext: str, name: str) -> str:
    """A recording as a levelled 24 kHz WAV on local disk (cached for the run)."""
    if name not in _cb["refs"]:
        r = httpx.get(url, timeout=60, follow_redirects=True)
        r.raise_for_status()
        a, _ = trim_silence(decode_bytes(r.content, "." + (ext or "wav")))
        out = config.WORK_DIR / f"voice_{name}.wav"
        _write_pcm(out, resample_to(level(a), SR, 24000), 24000)
        _cb["refs"][name] = str(out)
    return _cb["refs"][name]


def _cb_ref(vid: str) -> str:
    """The sample this voice is cloned from: the one that matched the person best in the voice check."""
    if vid == "default":
        return ""
    c = next((c for c in custom_voices() if c["id"] == vid), None)
    if not c:
        raise RuntimeError(f"voice {vid} not found, not checked yet, or has no recorded permission")
    smp = samples_of(c)
    best = smp[min(int(c.get("best") or 0), len(smp) - 1)]
    return sample_wav(best["url"], best.get("ext", "wav"), f"{vid}_{c.get('best') or 0}")


def _cb_call(job: dict, timeout_lines: int = 1) -> dict:
    import json as _json
    with _cb["lock"]:
        p = _cb_proc()
        p.stdin.write(_json.dumps(job) + "\n")
        p.stdin.flush()
        return _json.loads(p.stdout.readline() or '{"ok": false, "error": "Chatterbox exited"}')


def chatterbox_verify(refs: list[str], text: str) -> list[dict]:
    reply = _cb_call({"cmd": "verify", "refs": refs, "text": text, "out_dir": str(config.WORK_DIR)})
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error", "voice check failed"))
    return reply["results"]


def resample_to(a: np.ndarray, src: int, dst: int) -> np.ndarray:
    n = int(len(a) * dst / src)
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)


def _write_pcm(path: Path, a: np.ndarray, sr: int) -> None:
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())


def _chatterbox_tts(text, voice, rate, mood):
    out = Path(tempfile.mkstemp(suffix=".wav", dir=config.WORK_DIR)[1])
    reply = _cb_call({"text": text, "out": str(out), "ref": _cb_ref(voice)})
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error", "Chatterbox failed"))
    try:
        return decode_to_array(str(out)), None
    finally:
        out.unlink(missing_ok=True)


ENGINES = {"chatterbox": _chatterbox_tts, "elevenlabs": _elevenlabs_tts, "openai": _openai_tts, "gemini": _gemini_tts,
           "voxcpm": _voxcpm_tts, "kokoro": _kokoro_tts, "edge": _edge_tts}
FALLBACK_ORDER = ["kokoro", "edge"]


def _fallback_voice(engine: str, lang: str, gender: str) -> str | None:
    cands = [v for v in VOICES if v["engine"] == engine and v["lang"] == lang and v.get("note") != "blend"]
    pick = next((v for v in cands if v["gender"] == gender), cands[0] if cands else None)
    return pick["id"].split(":", 1)[1] if pick else None


def synth(text: str, voice: str, rate: str = "+0%", mood: str = "energetic",
          avoid: set | None = None) -> tuple[np.ndarray, list[dict], str]:
    """Returns (float32 mono audio @44.1k, word timings, engine used).

    avoid: engines to skip (Audio QA uses this to force a re-record on another engine)."""
    avoid = avoid or set()
    info = voice_info(voice)
    forced = os.getenv("TTS_ENGINE")  # e.g. TTS_ENGINE=espeak for tests
    chain: list[tuple[str, str]] = []
    if not forced:
        chain.append((info["engine"], info["id"].split(":", 1)[1]))
        if info.get("fallback"):                       # an uploaded voice falls back to a voice like it
            fb = voice_info(info["fallback"])
            chain.append((fb["engine"], fb["id"].split(":", 1)[1]))
        for eng in FALLBACK_ORDER:
            fv = _fallback_voice(eng, info["lang"], info["gender"])
            if fv and (eng, fv) not in chain:
                chain.append((eng, fv))
    elif forced in ENGINES:
        chain.append((forced, _fallback_voice(forced, info["lang"], info["gender"]) or info["id"].split(":", 1)[1]))
    errors = []
    for eng, vname in chain:
        fn = ENGINES.get(eng)
        if not fn or eng in avoid:
            continue
        try:
            audio, words = fn(text, vname, rate, mood)
            if audio is None or len(audio) < SR * 0.2:
                raise RuntimeError("empty audio")
            return audio, (words or align_words(text, audio)), eng
        except Exception as e:  # noqa: BLE001
            errors.append(f"{eng}: {str(e)[:120]}")
    if errors:
        print("[tts] fell back to espeak:", " | ".join(errors), flush=True)
    audio, _ = _espeak_tts(text, info["lang"] if info["lang"] != "en" else "en-us", rate, mood,
                           female=info["gender"] == "f")
    return audio, align_words(text, audio), "espeak"


def trim_silence(a: np.ndarray, thresh: float = 0.008) -> tuple[np.ndarray, float]:
    idx = np.where(np.abs(a) > thresh)[0]
    if len(idx) == 0:
        return a, 0.0
    start = max(0, idx[0] - int(0.02 * SR))
    end = min(len(a), idx[-1] + int(0.12 * SR))
    return a[start:end], start / SR


def _pause_after(text: str, last: bool, mood: str) -> float:
    if last:
        return 0.6
    t = text.rstrip()
    base = 0.3 if t.endswith(("?", "!")) else 0.24 if t.endswith((".", "…")) else 0.12
    if mood in ("mysterious", "dramatic", "chill"):
        base += 0.08
    return base + random.uniform(-0.03, 0.05)  # tiny human irregularity


# ---------------------------------------------------------------- humanizer
def breath(rnd: random.Random, dur: float = 0.26, level: float = 0.035) -> np.ndarray:
    """A soft in-breath: band-limited noise with a breathy formant and a quick swell.
    Real narrators breathe between thoughts; total silence there is what sounds synthetic."""
    n = int(dur * SR)
    noise = np.random.default_rng(rnd.randrange(1 << 30)).normal(0, 1, n)
    spec = np.fft.rfft(noise)
    f = np.fft.rfftfreq(n, 1 / SR)
    centre = rnd.uniform(1100, 1700)
    shape = np.exp(-((f - centre) / 900) ** 2) + 0.35 * np.exp(-((f - 3200) / 1400) ** 2)
    shape[f < 250] = 0
    x = np.fft.irfft(spec * shape, n)
    t = np.linspace(0, 1, n)
    env = np.sin(np.pi * np.clip(t * 1.15, 0, 1)) ** 1.6     # swell in, fall off a bit early
    x = x * env
    return (x / (np.max(np.abs(x)) or 1) * level).astype(np.float32)


def room_tone(n: int, level: float = 0.0009, seed: int = 7) -> np.ndarray:
    """Very quiet pink-ish noise floor so pauses sound like a room, not digital zero."""
    w = np.random.default_rng(seed).normal(0, 1, n).astype(np.float32)
    b = np.cumsum(w) * 0.02
    b -= np.convolve(b, np.ones(2048) / 2048, mode="same")      # remove the drift, keep the warmth
    x = 0.6 * w + b
    return (x / (np.std(x) or 1) * level).astype(np.float32)


def narrate(scenes: list[dict], voices: dict, rate: str, mood: str = "energetic", avoid: set | None = None,
            humanize: dict | None = None) -> dict:
    """Voice every scene and lay them out on one timeline (with breaths and room tone)."""
    hz = {"breaths": True, "room_tone": True, **(humanize or {})}
    rnd = _seed("".join(sc["text"] for sc in scenes))
    chunks, words, timeline, t = [], [], [], 0.0
    engines = set()
    breaths = 0
    for i, sc in enumerate(scenes):
        voice = voices.get(sc.get("speaker", "A")) or voices.get("A")
        audio, w, engine = synth(sc["text"], voice, rate, mood, avoid)
        engines.add(engine)
        audio, offset = trim_silence(audio)
        # 8 ms fades remove clicks at cut points
        f = min(len(audio) // 2, int(0.008 * SR))
        if f:
            audio[:f] *= np.linspace(0, 1, f)
            audio[-f:] *= np.linspace(1, 0, f)
        dur = len(audio) / SR
        for x in w:
            s, e = x["s"] - offset, x["e"] - offset
            words.append({"w": x["w"], "s": round(t + max(0, s), 3), "e": round(t + min(dur, max(e, s + 0.05)), 3), "scene": i})
        timeline.append({"start": round(t, 3), "end": round(t + dur, 3)})
        chunks.append(audio)
        last = i == len(scenes) - 1
        pad = _pause_after(sc["text"], last, mood)
        gap = np.zeros(int(pad * SR), np.float32)
        nxt = scenes[i + 1]["text"] if not last else ""
        # breathe before a longer next line, after a real pause, not on every cut, never on espeak
        if (hz["breaths"] and not last and engine != "espeak" and len(nxt.split()) >= 8 and pad >= 0.22
                and rnd.random() < 0.6):
            b = breath(rnd, dur=min(0.3, pad + 0.04), level=float(np.max(np.abs(audio)) or 0.5) * 0.07)
            gap = np.concatenate([gap, np.zeros(max(0, len(b) - len(gap)), np.float32)])
            gap[len(gap) - len(b):] += b
            pad = len(gap) / SR
            breaths += 1
        chunks.append(gap)
        t += dur + pad
    full = np.concatenate(chunks)
    peak = float(np.max(np.abs(full)) or 1.0)
    full = (full / peak * 0.89).astype(np.float32)
    if hz["room_tone"]:
        full = full + room_tone(len(full))
    return {"audio": full, "words": words, "timeline": timeline, "duration": len(full) / SR,
            "engine": "+".join(sorted(engines)), "breaths": breaths}
