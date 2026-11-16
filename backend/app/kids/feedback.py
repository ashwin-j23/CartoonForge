"""Parent & viewer feedback on episodes.

YouTube disables comments on every "made for kids" video, so feedback comes through a short public page for
grown-ups (frontend #/feedback?v=<episode>), linked from each video's description. Nothing personal is asked;
emails / phone numbers typed into the free-text boxes are blanked out (children's privacy, COPPA spirit).

Stored in the `feedback` table (docs/supabase.sql). If that table doesn't exist yet, answers are kept in the
activity log (level "feedback") so nothing is lost, and read back from there.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from .. import config
from ..db import get_db
from ..settings import app_settings

RATINGS = ("style", "animation", "voices", "learning")          # 1-5 stars each
ENJOYED = ("loved", "ok", "not_really")
AGES = ("toddler", "preschool", "early", "big")
ROLES = ("parent", "teacher", "other")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?\d[\s().-]*){7,}")
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)


def site_url() -> str:
    return (config.PUBLIC_BASE_URL or app_settings().get("site_url") or "").rstrip("/")


def link(eid: str) -> str:
    base = site_url()
    return f"{base}/#/feedback?v={eid}" if base else ""


def with_link(description: str, eid: str) -> str:
    """Add the grown-ups' feedback line after the opening paragraph (once)."""
    url = link(eid)
    if not url or url in (description or ""):
        return description or ""
    line = f"👨‍👩‍👧 Grown-ups: how was this episode? Tell us in 1 minute (what to change, what Hoppy should learn next) 👉 {url}"
    parts = (description or "").split("\n\n", 1)
    return f"{parts[0]}\n\n{line}" + (f"\n\n{parts[1]}" if len(parts) > 1 else "")


def scrub(text: str, limit: int) -> str:
    t = _EMAIL.sub("[removed]", str(text or ""))
    t = _PHONE.sub("[removed]", t)
    t = _URL.sub("[link removed]", t)
    return " ".join(t.split())[:limit]


def clean(body: dict) -> dict:
    """Validate a submitted form. Raises ValueError with a friendly message."""
    if not isinstance(body, dict):
        raise ValueError("Bad form")
    row = {"episode_id": str(body.get("episode_id") or "")[:20] or None}
    enjoyed = body.get("enjoyed")
    row["enjoyed"] = enjoyed if enjoyed in ENJOYED else None
    for k in RATINGS:
        v = body.get(k)
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = None
        row[k] = v if v is not None and 1 <= v <= 5 else None
    row["change"] = scrub(body.get("change"), 600)
    row["request"] = scrub(body.get("request"), 160)
    row["age_band"] = body.get("age_band") if body.get("age_band") in AGES else None
    row["role"] = body.get("role") if body.get("role") in ROLES else None
    if not (row["enjoyed"] or any(row[k] for k in RATINGS) or row["change"] or row["request"]):
        raise ValueError("Please answer at least one question")
    return row


def save(row: dict) -> dict:
    db = get_db()
    try:
        return db.insert("feedback", row)
    except Exception:  # noqa: BLE001  (table not created yet: keep it in the activity log)
        db.log("Feedback: " + json.dumps(row, ensure_ascii=False), "feedback", row.get("episode_id"))
        return row


def rows(limit: int = 500) -> list[dict]:
    db = get_db()
    out = []
    try:
        out = db.query("feedback", limit=limit)
    except Exception:  # noqa: BLE001
        pass
    for e in db.query("events", eq={"level": "feedback"}, limit=limit):
        try:
            out.append({**json.loads(e["msg"].split("Feedback: ", 1)[1]), "id": e["id"], "created_at": e["created_at"]})
        except (IndexError, ValueError):
            continue
    return sorted(out, key=lambda r: r.get("created_at") or "", reverse=True)[:limit]


def summary(items: list[dict]) -> dict:
    avg = {}
    for k in RATINGS:
        vals = [r[k] for r in items if isinstance(r.get(k), int)]
        avg[k] = round(sum(vals) / len(vals), 2) if vals else None
    enjoyed = Counter(r.get("enjoyed") for r in items if r.get("enjoyed"))
    req = Counter(" ".join(r["request"].lower().split()) for r in items if r.get("request"))
    by_ep = Counter(r.get("episode_id") for r in items if r.get("episode_id"))
    return {"count": len(items), "avg": avg, "enjoyed": dict(enjoyed),
            "loved_pct": round(100 * enjoyed.get("loved", 0) / max(1, sum(enjoyed.values()))),
            "requests": [{"topic": t, "n": n} for t, n in req.most_common(12)],
            "ages": dict(Counter(r.get("age_band") for r in items if r.get("age_band"))),
            "by_episode": dict(by_ep.most_common(20))}


def ai_summary(items: list[dict]) -> dict:
    """What parents are telling us, as themes + concrete changes + topic ideas (one model call)."""
    from ..llm.router import complete_json
    text = "\n".join(f"- enjoyed={r.get('enjoyed')} style={r.get('style')} animation={r.get('animation')} "
                     f"voices={r.get('voices')} learning={r.get('learning')} age={r.get('age_band')} | change: "
                     f"{r.get('change') or '-'} | next: {r.get('request') or '-'}" for r in items[:150])
    data, _ = complete_json(
        "You summarise parents' feedback on a preschool cartoon channel for its producer. Be specific and honest, "
        "never invent feedback that isn't there. JSON only.",
        f"Feedback ({len(items)} responses):\n{text}\n\nReturn {{\"themes\": [3-6 short sentences], "
        "\"changes\": [concrete changes to style / animation / voices / pacing / learning, most-requested first], "
        "\"topics\": [episode topics parents asked for], \"praise\": [what to keep doing]}",
        temperature=0.3, max_tokens=1500)
    return data if isinstance(data, dict) else {}
