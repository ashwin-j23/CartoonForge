"""Algorithmic reinforcement: the channel learns from its own YouTube data.

Every episode is made with a *variant* — pace, length, thumbnail style, title style — chosen by Thompson
sampling (multi-armed bandit): mostly the best-known option, sometimes a challenger (explore_rate), so the
channel keeps improving instead of freezing on an early guess. The reward is what the YouTube algorithm itself
rewards: how much of the video kids watch (average view %) times how fast it gathers views.

It also reads each video's retention curve (YouTube Analytics `audienceWatchRatio` over the timeline), lines it up
with the episode's segments, and learns which segment kinds hold children and which lose them. That becomes
plain-language guidance for the Writer ("songs hold best; keep recaps short") and the per-kind minute budget.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from ..db import get_db
from ..settings import app_settings

ARMS = {
    "pace": ["calm", "lively", "rapid"],
    "minutes": [6, 7, 8],                              # short episodes finish; the 7.5-min one won
    "thumb": ["face", "object", "duo"],
    "title": ["search", "character", "question"],
    "style": ["classic", "paper", "comic", "pixel", "anime", "ps2", "risograph"],
}
PRIOR_N = 2.0


def _state() -> dict:
    return get_db().get_setting("optimizer_state", {}) or {}


def reward(ep: dict) -> float | None:
    st = ep.get("stats") or {}
    if "views" not in st or not ep.get("published_at"):
        return None
    try:
        days = max(1.0, (datetime.now(timezone.utc) - datetime.fromisoformat(ep["published_at"])).total_seconds() / 86400)
    except ValueError:
        days = 7.0
    pct = float(st.get("avg_pct") or 35.0) / 100
    return pct * math.log1p(st["views"] / days)


def learn() -> dict:
    """Recompute arm statistics from every published episode with stats."""
    db = get_db()
    eps = [e for e in db.query("episodes", eq={"status": "published"}, limit=1000)
           if e.get("kind", "episode") == "episode" and e.get("variant")]
    rows = [(e["variant"], r) for e in eps if (r := reward(e)) is not None]
    glob = sum(r for _, r in rows) / len(rows) if rows else 0.0
    arms = {}
    for dim, opts in ARMS.items():
        arms[dim] = {}
        for o in opts:
            rs = [r for v, r in rows if str(v.get(dim)) == str(o)]
            n = len(rs)
            mean = (sum(rs) + PRIOR_N * glob) / (n + PRIOR_N)
            arms[dim][str(o)] = {"n": n, "mean": round(mean, 4)}
    state = {**_state(), "arms": arms, "global": round(glob, 4), "episodes": len(rows),
             "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    db.set_setting("optimizer_state", state)
    return state


def choose(dim: str, fixed: str | None = None, allowed: list | None = None) -> str:
    """Thompson-style pick: sample mean + noise shrinking with evidence; explore_rate forces a challenger now and then.
    allowed: limit the options (e.g. art styles that suit the episode's age band)."""
    if fixed and fixed != "auto":
        return fixed
    opts = [o for o in ARMS[dim] if allowed is None or o in allowed] or ARMS[dim]
    s = app_settings()
    if not s.get("optimizer", True):
        return str(opts[len(opts) // 2])
    arms = (_state().get("arms") or {}).get(dim) or {}
    if random.random() < float(s.get("explore_rate", 0.2)) or not arms:
        return str(random.choice(opts))
    scale = max(0.05, (_state().get("global") or 1.0) * 0.5)
    best, best_v = None, -1e9
    for o in opts:
        a = arms.get(str(o), {"n": 0, "mean": 0})
        v = a["mean"] + random.gauss(0, scale / math.sqrt(a["n"] + 1))
        if v > best_v:
            best, best_v = str(o), v
    return best


def variant(band: str = "preschool") -> dict:
    """The recipe for the next episode. art_style 'auto' lets the channel learn which LOOK holds children best,
    choosing only among looks that suit the age band (render/styles.py)."""
    from ..render.styles import for_band
    s = app_settings()
    from ..render.styles import STYLES
    style_fixed = s.get("art_style", "auto")
    if style_fixed not in STYLES:                       # a look that was removed: let the optimizer choose
        style_fixed = "auto"
    v = {"pace": choose("pace", s.get("pace")), "minutes": int(choose("minutes", str(int(s["target_minutes"]))
                                                                       if not s.get("optimizer", True) else None)),
         "thumb": choose("thumb"), "title": choose("title"),
         "style": choose("style", style_fixed if style_fixed != "auto" else None, for_band(band))}
    return v


# ---------------------------------------------------------------- retention curves -> segment kinds
def learn_segments(curves: dict[str, list[tuple[float, float]]], episodes: list[dict]) -> dict:
    """curves: youtube id -> [(elapsed ratio 0..1, audienceWatchRatio)]. Returns {kind: avg drop per minute (%)}."""
    agg: dict[str, list[float]] = {}
    for ep in episodes:
        vid = (ep.get("youtube") or {}).get("id")
        curve = curves.get(vid)
        dur = ep.get("duration") or 0
        if not curve or not dur or not ep.get("timeline"):
            continue

        def at(sec: float) -> float:
            x = sec / dur
            pts = sorted(curve)
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if x0 <= x <= x1:
                    return y0 + (y1 - y0) * ((x - x0) / max(1e-6, x1 - x0))
            return pts[-1][1] if x > pts[-1][0] else pts[0][1]
        for seg in ep["timeline"]:
            mins = (seg["end"] - seg["start"]) / 60
            if mins < .2:
                continue
            drop = (at(seg["start"]) - at(seg["end"])) * 100 / mins
            agg.setdefault(seg["kind"], []).append(drop)
    perf = {k: round(sum(v) / len(v), 2) for k, v in agg.items() if v}
    if perf:
        db = get_db()
        db.set_setting("optimizer_state", {**_state(), "segments": perf,
                                           "first_30s": _hook_drop(curves)})
    return perf


def _hook_drop(curves: dict) -> float | None:
    drops = []
    for c in curves.values():
        pts = sorted(c)
        if len(pts) > 3:
            drops.append((pts[0][1] - pts[min(3, len(pts) - 1)][1]) * 100)
    return round(sum(drops) / len(drops), 1) if drops else None


def writer_hints() -> str:
    st = _state()
    seg = st.get("segments") or {}
    if len(seg) < 3:
        return ""
    ranked = sorted(seg.items(), key=lambda kv: kv[1])
    good = ", ".join(k for k, _ in ranked[:3])
    weak = ", ".join(k for k, _ in ranked[-2:])
    out = f"Children stay longest in: {good}. They leave most during: {weak} — keep those short, lively and visual."
    if (st.get("first_30s") or 0) > 15:
        out += " Many leave in the first 30 seconds: make the opening tease stronger and faster."
    return out


def summary() -> dict:
    st = _state()
    return {"arms": st.get("arms") or {d: {str(o): {"n": 0, "mean": 0} for o in opts} for d, opts in ARMS.items()},
            "segments": st.get("segments") or {}, "first_30s_drop": st.get("first_30s"), "episodes": st.get("episodes", 0),
            "updated": st.get("updated"), "hints": writer_hints()}
