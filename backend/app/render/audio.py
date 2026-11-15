"""The episode soundtrack and its timeline.

Voice every line in its character's voice, then lay everything on one clock:
  theme jingle → segments (with a soft whoosh between) → slow theme reprise.
Question lines are followed by a real silence for the child to answer (age-based) with soft ticks; answers get
a chime. Song lines snap to the bars of the backing track, so the chant sits on the beat. Background music is
ducked under speech. Returns the timeline the renderer animates from (who talks when, mouth openness per
frame, when each counted object should pop in).
"""
from __future__ import annotations

import math
import re
import wave
from pathlib import Path

import numpy as np

from .. import tts
from ..kids import cast, categories, psychology
from . import music

SR = tts.SR
PITCH = {"pip": 1.07, "mimi": 1.03, "bo": 0.95, "zuzu": 1.0, "nana": 0.98, "sunny": 1.0}   # tiny pitch = personality
GAP_SEG = 0.9
NUMBER_WORDS = {w: i for i, w in enumerate(["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                                             "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                                             "seventeen", "eighteen", "nineteen", "twenty"])}


def _pitch(a: np.ndarray, p: float) -> np.ndarray:
    if abs(p - 1) < 1e-3:
        return a
    idx = np.arange(0, len(a) - 1, p)
    return np.interp(idx, np.arange(len(a)), a).astype(np.float32)


def _fade(a: np.ndarray, ms: float = 8) -> np.ndarray:
    f = min(len(a) // 2, int(ms / 1000 * SR))
    if f:
        a[:f] *= np.linspace(0, 1, f)
        a[-f:] *= np.linspace(1, 0, f)
    return a


class Track:
    def __init__(self, seconds: float = 60):
        self.buf = np.zeros(int(seconds * SR), np.float32)

    def add(self, x: np.ndarray, at: float, gain: float = 1.0):
        i = int(max(0, at) * SR)
        if i + len(x) > len(self.buf):
            self.buf = np.concatenate([self.buf, np.zeros(i + len(x) - len(self.buf) + SR * 30, np.float32)])
        self.buf[i:i + len(x)] += x * gain


def _reveal_times(card: dict | None, words: list[dict], start: float, dur: float) -> list[float]:
    """When each counted object pops in: on the spoken number words if present, else spread over the line."""
    if not card or card.get("type") != "count":
        return []
    n = int(card.get("n", 0) or 0)
    if n <= 0:
        return []
    hits = []
    for w in words:
        tok = re.sub(r"[^a-z0-9]", "", w["w"].lower())
        val = NUMBER_WORDS.get(tok, int(tok) if tok.isdigit() else None)
        if val is not None and 1 <= val <= n and val == len(hits) + 1:
            hits.append(w["s"])
    if len(hits) == n:
        return hits
    if n == 1 or len(hits) == 0:
        # a single "Seven!" line: show all n quickly at the start (the child counts them during the line)
        step = min(0.18, max(dur - 0.2, 0.2) / max(n, 1))
        return [start + 0.05 + i * step for i in range(n)]
    return [start + i * dur / n for i in range(n)]


VOICE_CHAIN = ("highpass=f=75,lowpass=f=14000,"
               "equalizer=f=250:t=q:w=1.2:g=-2.5,"           # less boxy
               "equalizer=f=3200:t=q:w=1.4:g=2.5,"           # presence: clear consonants for little ears
               "equalizer=f=9000:t=q:w=1.5:g=1.2,"           # air
               "deesser=i=0.35,"
               "acompressor=threshold=-21dB:ratio=3:attack=6:release=90:makeup=2.5,"
               "aecho=0.9:0.9:28:0.07")                       # a tiny room so it isn't bone dry


def voice_chain(v: np.ndarray) -> np.ndarray:
    """Studio polish for the narration (EQ, de-ess, compression, a touch of room) via ffmpeg. Falls back to
    the raw track if ffmpeg lacks a filter."""
    import subprocess
    from .. import config
    try:
        raw = (np.clip(v, -1, 1) * 32767).astype(np.int16).tobytes()
        r = subprocess.run([config.FFMPEG, "-v", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-",
                            "-af", VOICE_CHAIN, "-f", "f32le", "-ar", str(SR), "-ac", "1", "-"],
                           input=raw, capture_output=True, timeout=600)
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError(r.stderr.decode()[:200])
        out = np.frombuffer(r.stdout, np.float32)
        if len(out) < len(v):
            out = np.concatenate([out, np.zeros(len(v) - len(out), np.float32)])
        return out[:len(v)].copy()
    except Exception as e:  # noqa: BLE001
        print("[audio] voice chain skipped:", e)
        return v


def build(script: dict, settings: dict, out_wav: Path, fps: int, log=print) -> dict:
    lang = script.get("language", "en")
    b = psychology.band(script["age_band"])
    cat = categories.get(script["category"])
    mood = cat["mood"]
    rate = settings.get("voice_rate", "-4%")
    overrides = settings.get("voices") or {}
    channel = settings.get("channel_name", "Sunny Sprouts")
    seed = script.get("title_idea", "") + script.get("topic", "")
    pc = psychology.pace(settings.get("_pace") or settings.get("pace"))
    tempo = pc["tempo"] if mood not in ("bedtime",) else 1.0
    voice = Track(900)
    sfx = Track(900)
    regions: list[dict] = []          # music regions
    scenes_tl: list[dict] = []
    segs_tl: list[dict] = []
    engines: set[str] = set()

    jingle = music.theme(channel)
    jingle_len = len(jingle) / SR
    t = jingle_len - 0.5
    regions.append({"start": 0, "end": jingle_len, "kind": "theme"})

    guests = {g["id"]: g for g in script.get("characters") or [] if g.get("id")}

    def speak(sc: dict, at: float, voice_mood: str) -> tuple[float, list[dict]]:
        vid = cast.voice_for(sc["speaker"], overrides, lang, guests)
        a, words, eng = tts.synth(sc["text"], vid, rate, voice_mood)
        engines.add(eng)
        a, off = tts.trim_silence(a)
        if sc["speaker"] in guests and sc["speaker"] not in cast.CAST:
            p = cast.guest_profile(guests[sc["speaker"]])[1]
        else:
            p = PITCH.get(sc["speaker"], 1.0) if lang == "en" else 1.0
        a = _fade(_pitch(a, p))
        dur = len(a) / SR
        voice.add(a, at)
        ws = [{"w": w["w"], "s": round(at + max(0, (w["s"] - off) / p), 3), "e": round(at + min(dur, (w["e"] - off) / p), 3)}
              for w in words]
        return dur, ws

    for si, seg in enumerate(script["segments"]):
        if si > 0:
            sfx.add(music.sfx("whoosh", si), t, 0.8)
            t += GAP_SEG
        seg_start = t
        seg_mood = {"song": mood, "calm": "calm", "movement": "excited", "goodbye": "calm" if mood != "bedtime" else "bedtime"}.get(
            seg["kind"], mood)
        voice_mood = "bedtime" if mood == "bedtime" or seg["kind"] == "calm" else (
            "story" if seg["kind"] == "story" else "excited" if seg["kind"] == "movement" else "playful")
        song_start = None
        bar = music.bar_seconds("bedtime" if mood == "bedtime" else ("excited" if mood == "excited" else "playful"), tempo)
        for ci, sc in enumerate(seg["scenes"]):
            sing = sc.get("kind") == "sing" and seg["kind"] == "song"
            if sing and song_start is None:
                song_start = t + 0.2
                t = song_start + bar                       # one bar count-in
            if sing:
                k = math.ceil((t - song_start) / bar - 1e-6)
                t = song_start + k * bar + 0.05
            if sc.get("kind") == "answer":
                sfx.add(music.sfx("chime"), t - 0.15, 0.7)
            dur, ws = speak(sc, t, "playful" if sing else voice_mood)
            hold = t + dur
            if sc.get("kind") == "question":
                for k in range(int(b["pause"])):
                    sfx.add(music.sfx("tick"), hold + 0.5 + k, 0.8)
                hold += b["pause"]
            elif not sing:
                hold += 0.32 + (0.15 if sc["text"].rstrip().endswith(("!", "?", ".")) else 0.0)
                if voice_mood in ("bedtime", "story"):
                    hold += 0.2
            reveal = _reveal_times(sc.get("card"), ws, t, dur)
            for r in reveal:
                sfx.add(music.sfx("pop", int(r * 100)), r, 0.6)
            scenes_tl.append({"seg": si, "idx": ci, "speaker": sc["speaker"], "start": round(t, 3),
                              "voice_end": round(t + dur, 3), "end": round(hold, 3), "kind": sc.get("kind", "line"),
                              "words": ws, "reveal": [round(r, 3) for r in reveal], "sing": sing})
            t = hold
        if song_start is not None:
            end_bar = math.ceil((t - song_start) / bar) + 1
            regions.append({"start": seg_start, "end": song_start, "kind": "bed", "mood": seg_mood})
            regions.append({"start": song_start, "end": song_start + end_bar * bar, "kind": "song", "bars": end_bar,
                            "mood": mood})
            t = max(t, song_start + end_bar * bar)
            sfx.add(music.sfx("yay"), t - 0.6, 0.5)
        else:
            regions.append({"start": seg_start, "end": t, "kind": "bed", "mood": seg_mood, "seg": seg["kind"]})
        segs_tl.append({"title": seg["title"], "kind": seg["kind"], "set": seg.get("set"), "start": round(seg_start, 3),
                        "end": round(t, 3)})
        log(f"Voiced segment {si + 1}/{len(script['segments'])} '{seg['title']}' → {t / 60:.1f} min")

    outro = music.theme(channel, slow=True)
    regions.append({"start": t + 0.3, "end": t + 0.3 + len(outro) / SR, "kind": "outro"})
    total = t + 0.3 + len(outro) / SR + 0.5
    n = int(total * SR)

    # ---- music
    mus = np.zeros((n, 2), np.float32)               # music is stereo
    level = float(settings.get("music_level", 0.16)) if settings.get("music", True) else 0.0

    def put(x: np.ndarray, at: float, gain: float, fade: float = 0.35):
        i = int(at * SR)
        x = x[: max(0, n - i)].copy()
        if x.ndim == 1:
            x = np.stack([x, x], axis=1)
        f = min(len(x) // 2, int(fade * SR))
        if f:
            x[:f] *= np.linspace(0, 1, f)[:, None]
            x[-f:] *= np.linspace(1, 0, f)[:, None]
        mus[i:i + len(x)] += x * gain

    put(jingle, 0, 0.9, 0.01)
    put(outro, regions[-1]["start"], 0.8, 0.05)
    for r in regions:
        dur = r["end"] - r["start"]
        if dur <= 0.3 or r["kind"] in ("theme", "outro") or not level:
            continue
        if r["kind"] == "song":
            put(music.song_bed(r["mood"], seed, r["bars"], tempo), r["start"], min(0.6, level * 3.2), 0.05)
        else:
            g = level * (1.5 if r.get("seg") == "movement" else 0.6 if r["mood"] in ("calm", "bedtime") else 1.0)
            put(music.bed(r["mood"], seed + str(int(r["start"])), dur + 0.4, tempo if r["mood"] not in ("calm", "bedtime") else 1.0),
                r["start"], g)

    v = voice.buf[:n]
    if len(v) < n:
        v = np.concatenate([v, np.zeros(n - len(v), np.float32)])
    v = voice_chain(v)
    peak = float(np.max(np.abs(v)) or 1)
    v = v / peak * 0.85
    # duck music under speech (50 ms envelope)
    env = np.abs(v)
    k = int(0.05 * SR)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    duck = 1 - 0.55 * np.clip(env / 0.04, 0, 1)
    for r in regions:                               # songs and jingles are not ducked
        if r["kind"] in ("song", "theme", "outro"):
            i0, i1 = int(r["start"] * SR), int(r["end"] * SR)
            duck[i0:i1] = np.maximum(duck[i0:i1], 0.8)
    s = sfx.buf[:n]
    if len(s) < n:
        s = np.concatenate([s, np.zeros(n - len(s), np.float32)])
    mix = (v + s)[:, None] + mus * duck[:, None]          # voice + effects in the centre, music in stereo
    mix = mix / (float(np.percentile(np.abs(mix), 99.95)) or 1) * 0.9
    mix = np.tanh(mix * 1.15) / np.tanh(1.15) * 0.97      # soft limiter: no harsh peaks, fuller loudness
    pcm = (mix * 32767).astype(np.int16)                  # interleaved L R
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    # mouth openness per video frame from the voice track
    hop = SR / fps
    frames = int(total * fps) + 1
    mouth = np.zeros(frames, np.float32)
    for f in range(frames):
        i = int(f * hop)
        seg_ = v[i:i + int(hop)]
        if len(seg_):
            mouth[f] = float(np.sqrt(np.mean(seg_ ** 2)))
    ref = float(np.percentile(mouth[mouth > 0.003], 90)) if np.any(mouth > 0.003) else 1.0
    mouth = np.clip(mouth / (ref or 1), 0, 1)
    return {"wav": str(out_wav), "duration": total, "scenes": scenes_tl, "segments": segs_tl, "mouth": mouth,
            "jingle": jingle_len, "outro_start": regions[-1]["start"], "engines": sorted(engines),
            "song_regions": [{**r, "beat": music.bar_seconds("excited" if mood == "excited" else "playful", tempo) / 4}
                             for r in regions if r["kind"] == "song"]}
