"""Original music + sound effects, synthesized in STEREO (no licences, no Content ID claims, ever).

* theme()      the channel jingle: the same melody every episode (ritual), seeded by the channel name
* song_bed()   a sing-along backing track on an exact beat grid (the voice lines are placed on its bars)
* bed()        background music for talking segments, per mood (bedtime = music-box lullaby)
* sfx()        pop, chime, whoosh, boing, tick, sparkle, yay — gentle, never loud or startling (mono)

Sound design: warm electric-piano / marimba / glockenspiel / music-box leads with a little inharmonicity and
velocity variation (so it doesn't sound like a beeping toy), chorused pads spread wide, plucked round bass in
the centre, soft kick + brushed clap + hi-hats, all through a synthetic convolution reverb. Melodies use chord
tones + the major pentatonic with motif repetition (A A' B A): catchy because predictable.
Music functions return float32 arrays of shape (n, 2).
"""
from __future__ import annotations

import hashlib
import random
import re
from functools import lru_cache

import numpy as np

SR = 44100

MOODS = {
    #            bpm  root  progression (chord roots in semitones)  lead           level
    "playful": (112, 60, [0, 7, 9, 5], "epiano", 1.0),
    "excited": (120, 62, [0, 5, 7, 0], "marimba", 1.0),
    "teacher": (100, 60, [0, 5, 7, 5], "epiano", 0.9),
    "story": (84, 57, [0, 9, 5, 7], "pluck", 0.75),
    "bedtime": (66, 60, [0, 9, 5, 7], "musicbox", 0.6),
    "calm": (70, 60, [0, 5, 9, 7], "musicbox", 0.6),
}
MAJOR = [0, 2, 4, 5, 7, 9, 11]
PENTA = [0, 2, 4, 7, 9]


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _adsr(n: int, a=.005, d=.1, s=.6, r=.15, hold=None) -> np.ndarray:
    t = np.arange(n) / SR
    hold = hold if hold is not None else n / SR - r
    env = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    rel = np.clip((t - hold) / max(r, 1e-4), 0, 1)
    return (env * (1 - rel)).astype(np.float32)


# ---------------------------------------------------------------- instruments (mono)
def epiano(f: float, dur: float = 0.9, vel: float = 1.0) -> np.ndarray:
    """Soft electric-piano: sine body + bell partial that fades fast + gentle tremolo."""
    t = _t(dur)
    body = np.sin(2 * np.pi * f * t) + .25 * np.sin(2 * np.pi * f * 2.001 * t) * np.exp(-t * 3)
    bell = .35 * np.sin(2 * np.pi * f * 14.0 * t) * np.exp(-t * 28) * vel
    x = (body + bell) * np.exp(-t * 2.2) * (1 + .06 * np.sin(2 * np.pi * 5.2 * t))
    return (x * _adsr(len(t), .003, .4, .5, .2) * .6 * vel).astype(np.float32)


def marimba(f: float, dur: float = 0.6, vel: float = 1.0) -> np.ndarray:
    t = _t(dur)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t * 6) + .35 * np.sin(2 * np.pi * f * 3.98 * t) * np.exp(-t * 18)
    x += .08 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t * 40)          # mallet click
    return (x * np.clip(t / .002, 0, 1) * .8 * vel).astype(np.float32)


def glock(f: float, dur: float = 1.0, vel: float = 1.0) -> np.ndarray:
    t = _t(dur)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t * 3) + .4 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 6) \
        + .2 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 12)
    return (x * np.clip(t / .001, 0, 1) * .35 * vel).astype(np.float32)


def pluck(f: float, dur: float = 0.8, vel: float = 1.0) -> np.ndarray:
    t = _t(dur)
    x = sum((1 / k) * np.sin(2 * np.pi * f * k * (1 + .0007 * k * k) * t) * np.exp(-t * (2.2 + k * 1.6)) for k in range(1, 8))
    return (x * np.clip(t / .003, 0, 1) * .75 * vel).astype(np.float32)


def musicbox(f: float, dur: float = 1.4, vel: float = 1.0) -> np.ndarray:
    t = _t(dur)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t * 2.2) + .25 * np.sin(2 * np.pi * f * 3 * t) * np.exp(-t * 5)
    return (x * np.clip(t / .002, 0, 1) * .7 * vel).astype(np.float32)


def bass(f: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """Round plucked bass with a touch of soft saturation (audible on phone speakers)."""
    t = _t(dur)
    x = np.sin(2 * np.pi * f * t) + .35 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 4) + .12 * np.sin(2 * np.pi * f * 3 * t) * np.exp(-t * 8)
    x = np.tanh(x * 1.4) / np.tanh(1.4)
    return (x * _adsr(len(t), .006, .25, .55, .08) * .55 * vel).astype(np.float32)


def pad_voice(freqs: list[float], dur: float, detune: float) -> np.ndarray:
    """Warm pad: band-limited saw (few harmonics) per note, slow attack/release."""
    t = _t(dur)
    x = np.zeros(len(t), np.float32)
    for f in freqs:
        ff = f * detune
        x += sum((1 / k) * np.sin(2 * np.pi * ff * k * t + k) for k in range(1, 6)).astype(np.float32)
    x /= max(1, len(freqs)) * 1.6
    env = np.clip(t / .35, 0, 1) * np.clip((dur - t) / .45, 0, 1)
    return (x * env * .28).astype(np.float32)


def kick(dur: float = 0.3) -> np.ndarray:
    t = _t(dur)
    f = 95 * np.exp(-t * 20) + 46
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)
    return (np.tanh(x * 1.5) * .55).astype(np.float32)


def _noise(rnd: np.random.Generator, n: int, hp: bool = True) -> np.ndarray:
    x = rnd.normal(0, 1, n).astype(np.float32)
    return np.diff(x, prepend=0) if hp else x


def hat(rnd: np.random.Generator, open_: bool = False) -> np.ndarray:
    n = int((.18 if open_ else .05) * SR)
    x = np.diff(_noise(rnd, n), prepend=0)
    return (x * np.exp(-np.arange(n) / SR * (18 if open_ else 70)) * .03).astype(np.float32)


def clap(rnd: np.random.Generator) -> np.ndarray:
    n = int(.16 * SR)
    t = np.arange(n) / SR
    env = np.exp(-t * 28) + .6 * np.exp(-np.abs(t - .012) * 300) + .5 * np.exp(-np.abs(t - .024) * 300)
    return (_noise(rnd, n) * env * .07).astype(np.float32)


def shaker(rnd: np.random.Generator, dur: float = 0.06) -> np.ndarray:
    n = int(dur * SR)
    return (_noise(rnd, n) * np.exp(-np.arange(n) / SR * 60) * .04).astype(np.float32)


LEAD = {"epiano": epiano, "marimba": marimba, "pluck": pluck, "musicbox": musicbox, "glock": glock}


# ---------------------------------------------------------------- reverb + stereo
@lru_cache(maxsize=8)
def _ir(seconds: float, seed: int, damp: float) -> np.ndarray:
    """Synthetic room impulse response: decaying noise, slightly darkened."""
    n = int(seconds * SR)
    rnd = np.random.default_rng(seed)
    x = rnd.normal(0, 1, n).astype(np.float32)
    t = np.arange(n) / SR
    x *= np.exp(-t * (6.9 / seconds))
    k = max(1, int(damp * SR / 1000))
    x = np.convolve(x, np.ones(k) / k, mode="same")
    pre = int(.012 * SR)
    x[:pre] *= np.linspace(0, 1, pre)
    return (x / (np.sqrt(np.sum(x ** 2)) or 1)).astype(np.float32)


def _fftconv(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)].astype(np.float32)


def reverb_stereo(left: np.ndarray, right: np.ndarray, wet: float = .22, seconds: float = 1.6) -> np.ndarray:
    l = left + wet * _fftconv(left, _ir(seconds, 11, 0.6))
    r = right + wet * _fftconv(right, _ir(seconds, 23, 0.6))
    return np.stack([l, r], axis=1).astype(np.float32)


class Bus:
    """A stereo mix bus: add mono sources with a pan position (-1 left .. +1 right)."""

    def __init__(self, seconds: float):
        n = int(seconds * SR)
        self.l = np.zeros(n, np.float32)
        self.r = np.zeros(n, np.float32)

    def add(self, x: np.ndarray, at: float, gain: float = 1.0, pan: float = 0.0):
        i = int(at * SR)
        if i < 0 or i >= len(self.l):
            return
        k = min(len(x), len(self.l) - i)
        gl, gr = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)   # equal-power pan
        self.l[i:i + k] += x[:k] * gain * gl * 1.414
        self.r[i:i + k] += x[:k] * gain * gr * 1.414


def _chord(root: int, degree: int) -> list[int]:
    idx = MAJOR.index(degree % 12) if degree % 12 in MAJOR else 0
    return [root + MAJOR[(idx + k) % 7] + (12 if idx + k >= 7 else 0) for k in (0, 2, 4)]


def _melody_bar(rnd: random.Random, chord: list[int], density: int) -> list[tuple[float, int, float]]:
    """(beat, midi, velocity) for one bar: chord tones on strong beats, pentatonic steps between."""
    root = chord[0]
    pool = sorted({n + 12 for n in chord} | {root + 12 + p for p in PENTA})
    notes, beat = [], 0.0
    steps = [1.0, .5, .5, 1.0, .5, .5] if density > 1 else [1.0, 1.0, 1.0, 1.0]
    for st in steps:
        if beat >= 4:
            break
        strong = beat in (0.0, 2.0)
        n = rnd.choice([c + 12 for c in chord]) if strong else rnd.choice(pool)
        notes.append((beat, n, 1.0 if strong else .75 + rnd.random() * .15))
        beat += st
    return notes


def arrangement(mood: str, seed: str, bars: int, start_bar: int = 0, drums: bool = True, lead: bool = True,
                level: float = 1.0, tempo: float = 1.0) -> np.ndarray:
    bpm, root, prog, lead_name, mlevel = MOODS.get(mood, MOODS["playful"])
    bpm *= tempo
    beat = 60 / bpm
    bar = beat * 4
    rnd = _rng(seed + mood)
    nrnd = np.random.default_rng(rnd.randrange(1 << 30))
    bus = Bus(bars * bar + 2.5)
    motif_a = [_melody_bar(rnd, _chord(root, prog[i % 4]), 2) for i in range(4)]
    motif_b = [_melody_bar(rnd, _chord(root, prog[i % 4]), 2) for i in range(4)]
    form = ["A", "A", "B", "A"]
    inst = LEAD.get(lead_name, epiano)
    soft = mood in ("bedtime", "calm", "story")
    for b in range(bars):
        t0 = b * bar
        chord = _chord(root, prog[(b + start_bar) % 4])
        freqs = [hz(n) for n in chord]
        bus.add(pad_voice(freqs, bar + .5, 1.0), t0, .55, -.6)                 # chorus: two detuned pads, wide
        bus.add(pad_voice(freqs, bar + .5, 1.004), t0, .55, .6)
        bus.add(bass(hz(chord[0] - 12), bar * .48), t0, .75, 0)
        if not soft:
            bus.add(bass(hz(chord[0] - 12), beat * 1.4, .8), t0 + beat * 2, .6, 0)
            bus.add(bass(hz(chord[2] - 12), beat * .9, .7), t0 + beat * 3.5, .45, 0)
        if lead:
            phrase = (motif_a if form[(b // 4) % 4] == "A" else motif_b)[b % 4]
            for off, m, vel in phrase:
                bus.add(inst(hz(m), vel=vel), t0 + off * beat, .34, .25)
                if not soft and off in (0.0, 2.0) and b % 2 == 1:
                    bus.add(glock(hz(m + 12), .8, .6), t0 + off * beat, .16, -.35)   # sparkle answer
        if drums and not soft:
            for k in range(4):
                if k in (0, 2):
                    bus.add(kick(), t0 + k * beat, .9, 0)
                if k in (1, 3):
                    bus.add(clap(nrnd), t0 + k * beat, .8, .1)
            for k in range(8):
                bus.add(hat(nrnd, open_=(k == 7)), t0 + k * beat / 2, 1.0 if k % 2 else .55, .4)
                bus.add(shaker(nrnd), t0 + k * beat / 2 + beat / 4, .5, -.45)
    out = reverb_stereo(bus.l, bus.r, wet=.28 if soft else .2, seconds=2.2 if soft else 1.5)
    peak = float(np.max(np.abs(out)) or 1)
    return (out / peak * .8 * mlevel * level).astype(np.float32)


def bar_seconds(mood: str, tempo: float = 1.0) -> float:
    return 60 / (MOODS.get(mood, MOODS["playful"])[0] * tempo) * 4


def song_bed(mood: str, seed: str, bars: int, tempo: float = 1.0) -> np.ndarray:
    """Backing track for a sing-along."""
    return arrangement("excited" if mood == "excited" else ("bedtime" if mood == "bedtime" else "playful"),
                       seed, bars, drums=mood != "bedtime", lead=True, tempo=tempo)


def bed(mood: str, seed: str, seconds: float, tempo: float = 1.0) -> np.ndarray:
    """Background music. Higher tempo (lively/rapid pace) also brings the drums in under talking."""
    m = mood if mood in MOODS else "playful"
    bars = int(seconds / bar_seconds(m, tempo)) + 2
    drums = m in ("playful", "excited") or (tempo > 1.05 and m == "teacher")
    x = arrangement(m, seed, bars, drums=drums, lead=True, tempo=tempo)
    return x[: int(seconds * SR)]


_word_cache: dict[tuple, np.ndarray | None] = {}


def _vowel_at(a: np.ndarray) -> float:
    """Seconds from the start of a sung word to its loud vowel (what the ear hears as 'on the beat')."""
    hop = 220
    env = np.array([np.abs(a[i:i + hop]).mean() for i in range(0, max(1, len(a) - hop), hop)])
    if not len(env):
        return 0.0
    return float(np.argmax(env >= .5 * env.max()) * hop / SR)


def _sung(word: str, voice: str, semis: float) -> np.ndarray | None:
    """One chanted word in a character voice, pitched up `semis` semitones (kid-like). None if no TTS here."""
    key = (word, voice, round(semis, 2))
    if key not in _word_cache:
        a = None
        try:
            from .. import tts
            try:
                a, _ = tts._kokoro_tts(word, voice, "+0%", "excited")
            except Exception:  # noqa: BLE001  (no Kokoro: try eSpeak, else instruments only)
                a, _ = tts._espeak_tts(word, voice, "+0%", "excited")
            a = np.asarray(a, np.float32)
            nz = np.where(np.abs(a) > .02 * (np.max(np.abs(a)) or 1))[0]
            if len(nz):
                a = a[max(0, nz[0] - 200):nz[-1] + 400]           # trim silence: the word lands on the beat
            r = 2 ** (semis / 12)                                 # resample = pitch up (and a touch shorter)
            a = np.interp(np.arange(0, len(a) - 1, r), np.arange(len(a)), a).astype(np.float32)
            a /= max(1e-6, float(np.max(np.abs(a))))
        except Exception:  # noqa: BLE001
            a = None
        _word_cache[key] = a
    return _word_cache[key]


def _hook_words(channel: str) -> list[str]:
    """The sung hook = the channel name, word by word ('Hoppy Hop Hop' -> Hoppy / Hop / Hop!)."""
    words = [w for w in re.findall(r"[A-Za-z']+", channel)][:4] or ["Hello"]
    words[-1] += "!"
    return words


def theme(channel: str, slow: bool = False, voices: bool = True) -> np.ndarray:
    """The channel's jingle: a sing-along hook on the channel name.

    'Hop-py! Hop! Hop!' on a rising call (sol-sol, do, mi) with a boing on every 'Hop', then the same call a
    step higher with a second voice joining (a little kids' chorus), clap-clap, and a sparkle. Always the same
    notes, so it becomes the channel's signature sound. Original melody (no borrowed tunes)."""
    bpm = 92 if slow else 120
    beat = 60 / bpm
    lead = .12                                                    # room for the first word's soft 'H'
    bus = Bus(lead + 8 * beat + 3.0)
    root = 60                                                     # C
    words = _hook_words(channel)
    calls = [[7, 12, 16, 19][: len(words)], [9, 14, 17, 21][: len(words)]]   # rising call, then a step higher
    beats = [0, 1, 2, 2.5][: len(words)]
    nrnd = np.random.default_rng(3)
    for phrase, notes in enumerate(calls):
        b0 = phrase * 4
        for w, (b, n) in enumerate(zip(beats, notes)):
            at = lead + (b0 + b) * beat
            long = w == len(words) - 1
            if w == 0 and len(words[0]) > 3:                      # 'Hop-py': two eighths on the same note
                for k in range(2):
                    bus.add(marimba(hz(root + 12 + n), .35), at + k * beat / 2, .45, .2)
            else:
                bus.add(marimba(hz(root + 12 + n), .6 if long else .4), at, .5, .2)
            bus.add(epiano(hz(root + n), 1.2 if long else .7, .8), at, .3, -.2)
            bus.add(glock(hz(root + 24 + n), .9, .5), at, .1, .5)
            if w > 0:
                bus.add(sfx("boing", phrase * 4 + w), at, .32, .3 - w * .2)
            if voices:
                for v, (voice, semis, gain, pan) in enumerate([("am_puck*0.5+am_liam*0.5", 5.0, .95, -.1),
                                                                ("af_sky", 3.0, .6, .25)]):
                    if v == 1 and phrase == 0:
                        continue                                  # the friend joins the second time
                    a = _sung(words[w], voice, semis + (2 if phrase else 0))
                    if a is not None:
                        bus.add(a, max(0.0, at - _vowel_at(a)), gain * (.85 if slow else 1), pan)
    for i, deg in enumerate([0, 5]):                              # I ... IV (bright, lifts into the answer)
        ch = _chord(root, deg)
        bus.add(pad_voice([hz(m) for m in ch], beat * 4.3, 1.0), lead + i * beat * 4, .5, -.6)
        bus.add(pad_voice([hz(m) for m in ch], beat * 4.3, 1.004), lead + i * beat * 4, .5, .6)
        bus.add(bass(hz(ch[0] - 12), beat * 4), lead + i * beat * 4, .75, 0)
    if not slow:
        for k in range(8):
            if k % 2 == 0:
                bus.add(kick(), lead + k * beat, .6, 0)
            bus.add(hat(nrnd), lead + k * beat + beat / 2, .7, .4)
        for b in (3, 3.5, 7, 7.5):                                # clap-clap kids can copy
            bus.add(clap(nrnd), lead + b * beat, .7, 0)
    for j, n in enumerate([24, 28, 31, 36]):
        bus.add(glock(hz(root + n), 1.2), lead + 8 * beat - .05 + j * .07, .3, -.5 + j * .33)
    out = reverb_stereo(bus.l, bus.r, wet=.22, seconds=1.6)
    peak = float(np.max(np.abs(out)) or 1)
    return (out / peak * .85).astype(np.float32)


# ---------------------------------------------------------------- sound effects (mono)
def sfx(name: str, seed: int = 0) -> np.ndarray:
    rnd = np.random.default_rng(seed)
    if name == "pop":
        t = _t(.09)
        f = 500 + 900 * (t / .09)
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40) * .3).astype(np.float32)
    if name == "chime":
        out = np.zeros(int(1.3 * SR), np.float32)
        for j, n in enumerate((84, 88, 91)):
            x = glock(hz(n), 1.1) * .9
            i = int(j * .07 * SR)
            out[i:i + len(x)] += x[:len(out) - i]
        return out * .7
    if name == "whoosh":
        n = int(.55 * SR)
        x = rnd.normal(0, 1, n)
        spec = np.fft.rfft(x)
        f = np.fft.rfftfreq(n, 1 / SR)
        spec *= np.exp(-((f - 1800) / 1500) ** 2)
        x = np.fft.irfft(spec, n)
        env = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
        return (x / (np.max(np.abs(x)) or 1) * env * .16).astype(np.float32)
    if name == "boing":
        t = _t(.35)
        f = 220 + 180 * np.sin(t * 40) * np.exp(-t * 8)
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * .28).astype(np.float32)
    if name == "tick":
        t = _t(.06)
        return ((np.sin(2 * np.pi * 1600 * t) + .5 * np.sin(2 * np.pi * 2400 * t)) * np.exp(-t * 110) * .08).astype(np.float32)
    if name == "sparkle":
        out = np.zeros(int(1.0 * SR), np.float32)
        for i, n in enumerate([84, 88, 91, 96, 100]):
            x = glock(hz(n), .7) * .5
            j = int(i * .06 * SR)
            out[j:j + len(x)] += x[:len(out) - j]
        return out
    if name == "yay":
        a = sfx("sparkle", seed)
        b = sfx("chime")
        out = np.zeros(max(len(a), len(b)), np.float32)
        out[:len(a)] += a
        out[:len(b)] += b * .5
        return out * .8
    return np.zeros(1, np.float32)
