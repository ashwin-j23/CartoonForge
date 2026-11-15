"""Automatic, lifelike expressions.

A face that holds one expression for a whole line looks like a puppet. Real (and well-animated) faces:
  * change mid-sentence on the words that carry feeling ("wow" → surprised, "oh no" → worried, "hmm" → thinking)
  * react: listeners mirror the speaker a beat later (empathy: a sad friend makes the others look worried)
  * anticipate: while the child is asked a question, the asker waits hopefully, then lights up
  * blink on the change — the classic animator's trick that hides the switch and reads as natural

All of it is derived from the script and the word timings, so it is automatic for every line, every character,
every language the TTS gives word times for. Pure functions of (scene, t): cheap, deterministic, render-worker safe.
"""
from __future__ import annotations

import re

CUES: list[tuple[str, str]] = [   # (regex on a lowercased word window, emotion) — first match wins
    (r"\b(oh no|uh[- ]?oh|oops|careful|scared|stuck|worried|help me|oh dear)\b", "worried"),
    (r"\b(sad|sorry|cry|crying|lost|alone|miss(ed)?|broke|broken|hurt)\b", "sad"),
    (r"\b(yawn|sleepy|goodnight|night[- ]night|bedtime)\b", "sleepy"),
    (r"\b(breathe|gently|slowly|quiet|shh+|calm|relax|snuggle)\b", "calm"),
    (r"\b(well done|good job|you did it|we did it|clever|proud|you're right|that's right|great job)\b", "proud"),
    (r"\b(hmm+|maybe|wonder|i think|let's see|guess|which one|how many|what if)\b", "thinking"),
    (r"\b(wow|whoa|ooh+|oh|look|really|surprise|huge|giant|gigantic)\b", "surprised"),
    (r"\b(yay|hooray|woo+hoo+|amazing|awesome|fantastic|brilliant|yes|hurray|let's go|fun)\b", "excited"),
]
QUIET = {"calm", "sleepy"}                     # in calm/bedtime lines only gentle cues may fire
GENTLE = {"calm", "sleepy", "happy", "proud", "thinking"}
CUE_HOLD = 1.3                                 # seconds a cue expression holds before easing back
MIN_GAP = .6                                   # no two changes closer than this (no flicker)
REACT_DELAY = .35                              # listeners react a beat after the speaker
MIRROR = {"excited": "excited", "surprised": "surprised", "sad": "worried", "worried": "worried",
          "thinking": "thinking", "proud": "happy", "sleepy": "sleepy", "calm": "calm", "happy": "happy"}


def _cue(text: str) -> str | None:
    t = text.lower()
    for rx, emo in CUES:
        if re.search(rx, t):
            return emo
    return None


def speaker_track(sc: dict, data: dict) -> list[tuple[float, str]]:
    """[(time, emotion)] for the speaker of one scene, starting at the scene start."""
    base = data.get("emotion") or "happy"
    if data.get("action") == "think":
        base = "thinking"
    events = [(sc["start"], base)]
    words = sc.get("words") or []
    for i, w in enumerate(words):
        nxt = str(words[i + 1].get("w", "")) if i + 1 < len(words) else ""
        word = re.sub(r"[^\w'\- ]", "", str(w.get("w", "")))
        nxt = re.sub(r"[^\w-]", "", nxt)
        pair, single = _cue(f"{word} {nxt}"), _cue(word)
        # a phrase starting on this word ("oh no", "well done") beats a single word; a cue that sits only in the
        # next word waits for that word
        emo = pair if pair and pair != _cue(nxt) else single
        if not emo or emo == events[-1][1]:
            continue
        if base in QUIET and emo not in GENTLE:
            continue
        s = float(w["s"])
        if s - events[-1][0] < MIN_GAP:
            continue
        events.append((s, emo))
        back = s + CUE_HOLD
        if back < sc["voice_end"] - .2:
            events.append((back, base))
    txt = " ".join(str(w.get("w", "")) for w in words)
    if txt.rstrip().endswith("!") and base in ("happy", "proud") and sc["voice_end"] - events[-1][0] > MIN_GAP + .4:
        events.append((max(sc["start"], sc["voice_end"] - .7), "excited"))          # the line lands with energy
    if sc.get("kind") == "answer":
        events.append((sc["start"] + .05, "excited"))
    if sc.get("kind") == "question" and sc["end"] > sc["voice_end"] + .4:
        pause = sc["end"] - sc["voice_end"]
        events.append((sc["voice_end"] + .15, "happy"))                              # waits hopefully, smiling
        if pause > 1.6:
            events.append((sc["voice_end"] + pause * .45, "thinking"))
            events.append((sc["end"] - .45, "excited"))                              # anticipation of the answer
    events.sort(key=lambda e: e[0])
    return events


def at(track: list[tuple[float, str]], t: float) -> tuple[str, float]:
    """(emotion, time it started) at t."""
    cur, since = track[0][1], track[0][0]
    for s, e in track:
        if s > t:
            break
        if e != cur:
            cur, since = e, s
    return cur, since


def listener(track: list[tuple[float, str]], sc: dict, t: float, seed: int, in_pause: bool) -> tuple[str, float]:
    """A listener mirrors the speaker a beat later, with a personal variation so friends don't move in lockstep."""
    delay = REACT_DELAY + (seed % 3) * .12
    if in_pause:
        start = sc["voice_end"] + .25 + (seed % 3) * .15
        if t < start:
            return at(track, t - delay)[0] if t - delay >= track[0][0] else "happy", sc["voice_end"]
        # thinking with the child, then a hopeful smile
        return ("thinking", start) if (t - start) < max(1.0, (sc["end"] - start) * .7) else ("excited", sc["end"] - .5)
    emo, since = at(track, t - delay) if t - delay >= track[0][0] else ("happy", sc["start"])
    emo = MIRROR.get(emo, "happy")
    if sc.get("kind") == "answer":
        emo = "excited" if seed % 2 else "proud"
    # long stretches of plain listening: an occasional warm glance (calm ↔ happy), different per character
    if emo == "happy" and t - since > 3.5 and int((t + seed * 1.7) / 2.3) % 3 == 0:
        return "calm", since
    return emo, since + delay
