"""Safety gate for children's content (plain code, no model, cannot be talked out of it).

Blocks: violence/fear/gross words, dangerous behaviour kids could copy, requests for personal data or
engagement (COPPA: comments are off on made-for-kids videos anyway), commercial pressure and brands/IP,
clickbait titles. A 'block' stops the episode; a 'warn' is shown in Review.
"""
from __future__ import annotations

import re

_B = r"\b(?:{})\b"

# Growth calls-to-action are allowed (warn only, shown in Review). Subscribe/like still work on made-for-kids
# videos; the bell does not. The pipeline adds ONE parent-directed subscribe line itself (settings.growth_cta).
WARN = {
    "cta": ["subscribe", "like this video", "hit the like", "smash that", "share this video", "ring the bell",
            "notification bell"],
    "retention_bait": ["watch till the end", "wait till the end", "watch to the end", "don't skip"],
}

BLOCK = {
    "violence": ["kill", "killed", "killing", "murder", "blood", "bloody", "gun", "guns", "shoot", "shooting", "knife",
                 "knives", "sword fight", "weapon", "weapons", "bomb", "war", "kick him", "kick her", "stab",
                 "beat up", "hurt you", "punch you"],
    "fear": ["horror", "creepy", "nightmare", "demon", "zombie", "haunted", "terrifying", "scream", "screaming",
             "evil", "devil", "skeleton", "corpse", "dead body", "ghost"],
    "unsafe_words": ["stupid", "idiot", "dumb", "shut up", "ugly", "fatty", "loser", "hate you", "crybaby"],
    "adult": ["sexy", "kiss me", "beer", "wine", "alcohol", "drunk", "cigarette", "smoking", "vape", "drug", "drugs",
              "casino", "gamble", "betting"],
    "danger": ["try this at home", "play with fire", "play with matches", "use a lighter", "electric socket",
               "plug socket", "take medicine by yourself", "eat the pills", "swallow it", "climb the window", "climb on the roof",
               "talk to strangers", "go with a stranger", "lick the", "put it in your mouth", "plastic bag over"],
    "personal_data": ["your address", "your phone number", "your full name", "what school", "your school's name",
                      "send us a photo", "send a picture", "tell us your name", "where do you live", "how old are you in the comments"],
    # comments are switched OFF by YouTube on made-for-kids videos (COPPA) -> asking for them only hurts quality
    "comments": ["comment below", "in the comments", "leave a comment", "write a comment", "tell us in the comments"],
    "commercial": ["buy", "ask your parents to buy", "ask your mom to buy", "ask your dad to buy", "in stores now",
                   "unboxing", "surprise eggs", "toy review", "sponsored", "discount code"],
    "brands": ["disney", "pixar", "peppa", "paw patrol", "cocomelon", "bluey", "barbie", "lego", "mcdonald",
               "coca-cola", "pepsi", "nintendo", "pokemon", "pokémon", "minecraft", "roblox", "fortnite", "marvel",
               "spider-man", "spiderman", "elsa", "frozen", "mickey", "baby shark", "pinkfong", "sesame street",
               "blippi", "ms rachel", "dora the explorer"],
}
# allowed in the science/dinosaur context for older bands (e.g. "the dinosaurs died out" is fine at 5-8)
SOFT = {"die", "died", "dead", "death", "scared", "monster", "monsters", "volcano", "fire", "lion roars"}

TITLE_RULES = [
    (re.compile(r"\b[A-Z]{5,}\b"), "ALL-CAPS word in the title"),
    (re.compile(r"!{2,}|\?{2,}"), "Repeated !! or ?? in the title"),
    (re.compile(r"(gone wrong|you won'?t believe|shocking|insane|crazy|scary|prank|challenge)", re.I), "Clickbait phrase"),
    (re.compile(r"([\U0001F300-\U0001FAFF].*){4,}"), "Too many emojis"),
]


def _find(text: str) -> list[tuple[str, str]]:
    low = text.lower()
    hits = []
    for cat, words in BLOCK.items():
        for w in words:
            if re.search(_B.format(re.escape(w)), low):
                hits.append((cat, w))
    return hits


def check_text(text: str) -> list[dict]:
    out = []
    low = text.lower()
    for cat, words in WARN.items():
        for w in words:
            if re.search(_B.format(re.escape(w)), low):
                out.append({"level": "warn", "rule": cat, "word": w})
    for cat, w in _find(text):
        # "buy" inside a story about a market ("Mama buys mangoes") is fine; the call-to-action is not
        if cat == "commercial" and w == "buy" and not re.search(r"\b(you|your parents|mom|dad|grown-?up)\b[^.]{0,30}\bbuy\b", text.lower()):
            continue
        out.append({"level": "block", "rule": cat, "word": w})
    return out


def check_title(title: str) -> list[dict]:
    issues = [{"level": "warn", "rule": "title", "word": msg} for rx, msg in TITLE_RULES if rx.search(title or "")]
    if len(title or "") > 100:
        issues.append({"level": "block", "rule": "title", "word": "Title longer than 100 characters"})
    return issues


def check_episode(ep: dict) -> dict:
    """Run the gate over the whole script + metadata. Returns {ok, issues}."""
    script = ep.get("script") or {}
    issues = []
    for seg in script.get("segments", []):
        for sc in seg.get("scenes", []):
            for i in check_text(sc.get("text", "")):
                issues.append({**i, "where": f"{seg.get('kind')}: \"{sc.get('text', '')[:80]}\""})
            card = (sc.get("visual") or {}).get("card") or {}
            for i in check_text(" ".join(str(v) for v in card.values())):
                issues.append({**i, "where": "on-screen card"})
    for g in script.get("characters") or []:
        for i in check_text(f"{g.get('name', '')} {g.get('personality', '')}"):
            issues.append({**i, "where": f"character {g.get('name', '')}"})
    meta = ep.get("meta") or {}
    for field in ("title", "description"):
        for i in check_text(meta.get(field, "")):
            issues.append({**i, "where": field})
    issues += check_title(meta.get("title", ""))
    return {"ok": not any(i["level"] == "block" for i in issues), "issues": issues}
