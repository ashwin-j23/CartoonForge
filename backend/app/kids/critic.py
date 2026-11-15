"""Critic: grades a script like a child-development consultant would, and sends weak segments back.

Score = average of the model's rubric and the measurable psychology checks (kids/psychology.analyze), so a
script cannot pass on charm alone if it breaks the pacing / participation / repetition rules.
"""
from __future__ import annotations

from ..llm.router import LLMError, complete_json
from . import psychology

RUBRIC = {
    "age_fit": "Words, sentence length and ideas fit the age band",
    "participation": "The child is asked to answer, count, sing, move — and given time to",
    "clarity": "One idea at a time, shown and said together, repeated with variety",
    "warmth": "Kind, safe, encouraging; effort is praised; feelings are named",
    "fun": "Gentle humour, surprise and play every couple of minutes",
    "flow": "Segments connect; wonder questions are answered; calm ending",
    "world": "Inclusive, globally relatable, no stereotypes",
}


def review(script: dict, band_id: str) -> dict:
    metrics = psychology.analyze(script, band_id)
    code_score = psychology.score(metrics)
    model = {"scores": {}, "segment_notes": {}, "summary": ""}
    try:
        compact = [{"i": i, "kind": s["kind"], "title": s["title"],
                    "lines": [f"{sc['speaker']}({sc['kind']}): {sc['text']}" for sc in s["scenes"]]}
                   for i, s in enumerate(script["segments"])]
        b = psychology.band(band_id)
        data, _ = complete_json(
            "You are a strict children's-media consultant (child development PhD, 20 years of preschool TV). "
            "Grade honestly; 7 is good, 9 is outstanding. Reply with JSON only.",
            f"Audience: {b['label']}. Episode: {script.get('title_idea')}. Key words: {script.get('key_words')}.\n"
            f"Rubric (0-10 each): {RUBRIC}\nAutomatic checks found: {metrics['issues']}\n\nSCRIPT:\n{compact}\n\n"
            "Return {\"scores\": {criterion: number}, \"summary\": str, "
            "\"segment_notes\": {\"<segment index>\": \"concrete fix instructions\"} (only segments that need a rewrite)}",
            temperature=0.2, max_tokens=2500, avoid=script.get("_writer_provider"))
        model = {"scores": {k: float(v) for k, v in (data.get("scores") or {}).items() if k in RUBRIC},
                 "segment_notes": {int(k): str(v) for k, v in (data.get("segment_notes") or {}).items()
                                   if str(k).isdigit()},
                 "summary": str(data.get("summary", ""))}
    except (LLMError, ValueError, TypeError) as e:
        model["summary"] = f"(model review unavailable: {str(e)[:120]})"
    ms = model["scores"]
    model_score = round(sum(ms.values()) / len(ms), 2) if ms else None
    final = round((code_score + model_score) / 2, 2) if model_score is not None else code_score
    return {"score": final, "code_score": code_score, "model_score": model_score, "rubric": ms,
            "metrics": metrics, "summary": model["summary"], "segment_notes": model["segment_notes"]}


def notes_from_metrics(script: dict, metrics: dict) -> dict[int, str]:
    """When the model gives no per-segment notes, route the automatic issues to the segments that can fix them."""
    notes: dict[int, str] = {}
    kinds = [s["kind"] for s in script["segments"]]
    for issue in metrics.get("issues", []):
        low = issue.lower()
        target = None
        if "song" in low and "song" not in kinds:
            continue
        if "interaction" in low or "question" in low:
            target = next((i for i, k in enumerate(kinds) if k in ("learn", "explore", "game")), None)
        elif "repeated" in low:
            target = next((i for i, k in enumerate(kinds) if k == "recap"), None)
        elif "effort" in low or "praise" in low:
            target = next((i for i, k in enumerate(kinds) if k == "goodbye"), None)
        elif "feeling" in low:
            target = next((i for i, k in enumerate(kinds) if k in ("story", "feelings", "learn")), None)
        elif "too long" in low or "too hard" in low:
            target = max(range(len(kinds)), key=lambda i: sum(len(sc["text"]) for sc in script["segments"][i]["scenes"]))
        if target is not None:
            notes[target] = (notes.get(target, "") + " " + issue).strip()
    return notes
