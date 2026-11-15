"""The story cast library: every character the show has ever needed, kept forever.

Tiers
  main       the core cast (Sunny, Pip, Mimi, Bo, Zuzu, Nana Owl) + anyone promoted to main
  recurring  story characters who come back (auto-promoted after RECUR_AFTER episodes, or by hand)
  cameo      designed for one story; saved, and reused automatically when the same character returns

Why: children bond with characters that look and sound the same every time. A Wolf designed for "The Boy Who
Cried Wolf" is the same Wolf when he turns up in another fable, with the same colours, outfit and voice.
"""
from __future__ import annotations

import re

from ..db import get_db, now_iso
from . import cast

TIERS = ("main", "recurring", "cameo")
RECUR_AFTER = 3
FIELDS = ("name", "kind", "species", "gender", "age", "colors", "outfit", "skin", "hair", "hair_color",
          "personality", "look", "catchphrase", "voice", "pitch")
EDITABLE = (*FIELDS, "tier")
CORE_EDITABLE = ("personality", "catchphrase", "voice", "look")


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(c[:3]) if isinstance(c, (list, tuple)) else str(c)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(s or "").lower().replace(" ", "_").replace("-", "_"))[:20] or "friend"


def _key(name: str) -> str:
    """Matching key: 'The Big Bad Wolf' ~ 'wolf', 'Mr. Fox' ~ 'fox'."""
    w = re.sub(r"\b(the|a|an|mr|mrs|ms|miss|little|old|big|bad|good|young|wise|sir|lady)\b", " ", str(name or "").lower())
    return re.sub(r"[^a-z]", "", w)


# ---------------------------------------------------------------- core cast rows (not stored; built from cast.py)
def _core(cid: str) -> dict:
    c = cast.CAST[cid]
    over = (get_db().get_setting("core_overrides") or {}).get(cid, {})
    return {"id": cid, "name": c["name"], "tier": "main", "core": True, "kind": "cast", "species": c["species"],
            "gender": c["gender"], "age": "child" if cid in ("pip", "hoppy") else "adult",
            "colors": {k: _hex(v) for k, v in c["colors"].items()}, "role": c["role"],
            "personality": over.get("personality") or c["personality"], "look": over.get("look") or c["look"],
            "catchphrase": over.get("catchphrase") or c["catchphrase"], "voice": over.get("voice") or c["voice"],
            "pitch": 1.0, "origin": {"type": "core"}, "appearances": None, "episodes": [],
            "portrait_url": f"/api/cast/{cid}.png"}


def _out(row: dict) -> dict:
    r = dict(row)
    r.setdefault("tier", "cameo")
    r["core"] = False
    r["appearances"] = len(r.get("episodes") or [])
    r["portrait_url"] = f"/api/cast/{r['id']}.png"
    return r


# ---------------------------------------------------------------- queries
def all_chars(tier: str | None = None, q: str = "") -> list[dict]:
    rows = [_core(c) for c in cast.CAST] + [_out(r) for r in get_db().query("characters", limit=1000)]
    if tier:
        rows = [r for r in rows if r["tier"] == tier]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in f"{r['name']} {r.get('species', '')} {r.get('personality', '')} "
                f"{(r.get('origin') or {}).get('story', '')}".lower()]
    order = {t: i for i, t in enumerate(TIERS)}
    return sorted(rows, key=lambda r: (order.get(r["tier"], 9), not r["core"], -(r.get("appearances") or 0)))


def get(cid: str) -> dict | None:
    if cid in cast.CAST:
        return _core(cid)
    r = get_db().get("characters", cid)
    return _out(r) if r else None


def spec(row: dict) -> dict:
    """The design spec the renderer/voice need (what goes in script['characters'])."""
    return {"id": row["id"], **{k: row[k] for k in FIELDS if row.get(k) not in (None, "")}}


def regulars() -> list[dict]:
    """Non-core main + recurring characters: the writer may use them in any episode."""
    return [r for r in all_chars() if not r["core"] and r["tier"] in ("main", "recurring")]


def bible() -> str:
    regs = regulars()
    if not regs:
        return ""
    return ("RECURRING FRIENDS (from earlier stories; reuse them by id when they fit, never redesign them):\n" +
            "\n".join(f"- {r['id']}: {r['name']} ({r.get('species') or r.get('kind', '')}). {r.get('personality', '')}"
                      for r in regs[:12]))


def match(g: dict) -> dict | None:
    """An existing library character for an outline character (same id, or same name key + species)."""
    db = get_db()
    gid = slug(g.get("id") or g.get("name"))
    if gid in cast.CAST:
        return None
    hit = db.get("characters", gid)
    if hit:
        return _out(hit)
    k = _key(g.get("name"))
    sp = str(g.get("species") or "").lower()
    for r in db.query("characters", limit=1000):
        if k and _key(r.get("name")) == k and (not sp or not r.get("species") or sp == str(r["species"]).lower()):
            return _out(r)
    return None


# ---------------------------------------------------------------- writes
def _clean(body: dict) -> dict:
    out = {}
    for k in EDITABLE:
        if k not in body:
            continue
        v = body[k]
        if k == "tier" and v not in TIERS:
            continue
        if k == "colors":
            v = {n: str(c)[:9] for n, c in (v or {}).items() if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)}
        elif k == "pitch":
            try:
                v = max(.8, min(1.25, float(v)))
            except (TypeError, ValueError):
                continue
        elif isinstance(v, str):
            v = v.strip()[:400]
        out[k] = v
    return out


def create(body: dict, origin: dict | None = None, tier: str = "recurring") -> dict:
    data = _clean(body)
    if not data.get("name"):
        raise ValueError("A character needs a name")
    db = get_db()
    cid = slug(body.get("id") or data["name"])
    base, n = cid, 2
    while cid in cast.CAST or db.get("characters", cid):
        cid = f"{base[:18]}{n}"
        n += 1
    row = {"id": cid, "tier": data.pop("tier", tier), **data, "origin": origin or {"type": "custom"}, "episodes": [],
           "updated_at": now_iso()}
    return _out(db.insert("characters", row))


def update(cid: str, body: dict) -> dict:
    db = get_db()
    if cid in cast.CAST:
        over = db.get_setting("core_overrides") or {}
        over[cid] = {**over.get(cid, {}), **{k: str(body[k])[:400] for k in CORE_EDITABLE if k in body}}
        db.set_setting("core_overrides", over)
        return _core(cid)
    if not db.get("characters", cid):
        raise KeyError(cid)
    return _out(db.update("characters", cid, {**_clean(body), "updated_at": now_iso()}))


def delete(cid: str) -> None:
    if cid in cast.CAST:
        raise ValueError("The core cast can't be deleted")
    get_db().delete("characters", cid)


def harvest(script: dict, episode_id: str, source: dict | None = None) -> list[str]:
    """After writing: save every story character of the episode to the library (new ones as cameo), record the
    appearance, and promote characters that keep coming back. Returns the ids touched."""
    db = get_db()
    touched = []
    spoken = {sc.get("speaker") for seg in script.get("segments", []) for sc in seg.get("scenes", [])} | \
             {c for seg in script.get("segments", []) for sc in seg.get("scenes", []) for c in sc.get("cast") or []}
    for g in script.get("characters") or []:
        cid = g.get("id")
        if not cid or cid in cast.CAST:
            continue
        row = db.get("characters", cid)
        if row is None:
            origin = {"type": "book" if source else "story", "episode_id": episode_id,
                      "story": (source or {}).get("title") or script.get("title_idea") or script.get("topic"),
                      **({"book": source.get("book")} if source and source.get("book") else {})}
            data = {k: g[k] for k in FIELDS if g.get(k) not in (None, "")}
            row = db.insert("characters", {"id": cid, "tier": "cameo", **data, "name": g.get("name") or cid,
                                           "origin": origin, "episodes": [], "updated_at": now_iso()})
        eps = list(row.get("episodes") or [])
        if episode_id not in eps and cid in spoken:
            eps.append(episode_id)
            patch = {"episodes": eps, "updated_at": now_iso()}
            if row.get("tier", "cameo") == "cameo" and len(eps) >= RECUR_AFTER:
                patch["tier"] = "recurring"
                db.log(f"{row.get('name')} keeps coming back: promoted to a recurring character", episode_id=episode_id)
            db.update("characters", cid, patch)
        touched.append(cid)
    return touched


def attach(script: dict) -> dict:
    """Make sure every library character used in the script carries its library design (so the renderer and the
    voices use the saved look and voice, not a fresh redesign)."""
    chars = {g["id"]: g for g in script.get("characters") or [] if g.get("id")}
    used = {sc.get("speaker") for seg in script.get("segments", []) for sc in seg.get("scenes", [])} | \
           {c for seg in script.get("segments", []) for sc in seg.get("scenes", []) for c in sc.get("cast") or []}
    db = get_db()
    for cid in used | set(chars):
        if not cid or cid in cast.CAST:
            continue
        row = db.get("characters", cid)
        if row:
            chars[cid] = {**chars.get(cid, {}), **spec(_out(row))}
    script["characters"] = list(chars.values())
    return script


# ---------------------------------------------------------------- design from a story
KEYWORDS = ("lion", "mouse", "fox", "crow", "wolf", "tortoise", "hare", "ant", "grasshopper", "bear", "rabbit", "frog",
            "owl", "dog", "cat", "goat", "sheep", "pig", "cow", "horse", "donkey", "monkey", "elephant", "crocodile",
            "tiger", "deer", "duck", "hen", "rooster", "peacock", "bee", "butterfly", "fish", "whale", "dragon",
            "unicorn", "squirrel", "panda", "penguin", "snake", "kangaroo", "camel", "giraffe", "zebra", "turtle",
            "king", "queen", "prince", "princess", "farmer", "boy", "girl", "giant", "wizard", "fairy", "baker",
            "fisherman", "grandmother", "grandfather", "woodcutter", "merchant", "shepherd", "miller", "tailor")
HUMAN = {"king", "queen", "prince", "princess", "farmer", "boy", "girl", "giant", "wizard", "fairy", "baker",
         "fisherman", "grandmother", "grandfather", "woodcutter", "merchant", "shepherd", "miller", "tailor"}
FEMALE = {"queen", "princess", "girl", "fairy", "grandmother", "hen"}
SKIN_CYCLE = ("brown", "light", "deep", "tan", "olive", "pale")


def _keyword_design(text: str) -> list[dict]:
    low = text.lower()
    found = sorted({k for k in KEYWORDS if re.search(rf"\b{k}s?\b", low)}, key=lambda k: low.find(k))[:6]
    out = []
    for i, k in enumerate(found):
        g = {"name": k.title(), "species": k, "kind": "human" if k in HUMAN else "animal",
             "gender": "f" if k in FEMALE else "m", "age": "old" if k.startswith("grand") else
             ("child" if k in ("boy", "girl") else "adult"), "personality": f"the {k} of the story"}
        if g["kind"] == "human":
            g.update(skin=SKIN_CYCLE[i % len(SKIN_CYCLE)], hair="curly" if i % 2 else "short")
        out.append(g)
    return out


def design_from_story(title: str, text: str, book: str = "") -> dict:
    from ..llm.router import complete_json
    from .writer import clean_characters
    text = (text or "")[:20000]
    chars: list[dict] = []
    try:
        from ..pipeline import has_ai
        if has_ai():
            data, _ = complete_json(
                "You are the character designer of a warm preschool TV show. Reply with JSON only.",
                f"Story: \"{title}\"{(' from ' + book) if book else ''}.\n{text[:12000]}\n\n"
                "Design EVERY character this story needs (max 6), friendly and not scary, in the same round, big-eyed "
                "picture-book style as the show. Return {\"characters\": [{\"id\", \"name\", \"kind\": animal|human, "
                "\"species\", \"gender\": f|m, \"age\": child|adult|old, \"colors\": {\"main\": \"#rrggbb\", \"accent\": "
                "\"#rrggbb\"}, \"outfit\": none|crown|cape|dress|robe|scarf|bow|glasses|wizard_hat|cap|straw_hat|chef_hat|"
                "turban|helmet|feathers, humans also \"skin\": deep|brown|tan|olive|light|pale, \"hair\": short|long|curly|"
                "bun|braids|afro|ponytail|spiky|bald, \"hair_color\", \"personality\": one sentence, \"look\": one-line "
                "visual description, \"catchphrase\": a short kind line it could say}]}. Show the world's diversity.",
                temperature=.7, max_tokens=1800)
            chars = data.get("characters") or []
    except Exception as e:  # noqa: BLE001
        get_db().log(f"AI character design failed, using the keyword designer: {str(e)[:160]}", "warn")
    if not chars:
        chars = _keyword_design(f"{title} {text}")
    created, reused, out = 0, 0, []
    origin = {"type": "book" if book else "story", "story": title[:120], **({"book": book[:120]} if book else {})}
    for g in clean_characters(chars):
        hit = match(g)
        if hit:
            reused += 1
            out.append(hit)
        else:
            created += 1
            out.append(create({**g, "id": g["id"]}, origin, tier="cameo"))
    return {"characters": out, "created": created, "reused": reused}
