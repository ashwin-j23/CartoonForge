"""App settings (editable from the dashboard) + secret resolution."""
from __future__ import annotations

import copy
import os
import time

from . import config
from .db import get_db

DEFAULTS: dict = {
    "channel_name": "Hoppy Hop Hop",
    "channel_handle": "@HoppyHopHopTV",
    "site_url": "",
    "feedback_cta": True,                 # end card asks grown-ups for feedback (link in the description)                       # the dashboard's public address (saved by Vercel; used for feedback links)  # youtube.com/@HoppyHopHopTV (used in descriptions)
    "channel_tagline": "Songs, stories and smiles for curious little minds",
    "language": "en",                     # main episode language (ISO 639-1)
    "timezone": "America/New_York",       # posting times follow this zone (auto-moved to where viewers are)
    "full_auto": False,                   # Full auto mode (app/automation.py): plan → make → gates → publish, hands-off
    "auto_retry": True,                   # failed episodes go round again (max_retries, 30 min apart)
    "max_retries": 2,
    "autopilot": False,                   # False = every episode waits in Review for a human OK (recommended for kids)
    "auto_generate": True,                # the planner keeps the pipeline full
    "episodes_per_week": 21,              # kept for the dashboard; scheduling uses episodes_per_day x post_days
    "episodes_per_day": 3,                # long episodes a day (one per posting time)
    "post_days": [0, 1, 2, 3, 4, 5, 6],   # 0 = Monday
    "post_times": ["08:00", "11:00", "16:00"],   # local: breakfast, late morning, after school/nap (parents press play)
    "bedtime_post_time": "",                     # bedtime episodes go out at this slot ("" = the latest post time)
    "auto_timezone": True,                # move posting times to the country most views come from
    "post_time": "07:30",                 # (legacy single slot)
    "trend_share": 0.6,                   # share of new episodes taken from the trend analyser (rest = balanced mix)
    "variety_max": 0.32,                  # block a script whose lines overlap > 32% with a recent one (inauthentic-content guard)
    "ai_backgrounds": False,              # illustrated backgrounds from an AI image model (Gemini or OpenAI key; ~$0.04 each)
    "target_minutes": 12,                 # 10-15 minute episodes
    "age_band": "preschool",              # default audience: toddler | preschool | early | big (see kids/psychology.py)
    "category_mix": {},                   # category -> weight override (empty = planner's balanced mix)
    "youtube_privacy": "public",
    "made_for_kids": True,                # COPPA: must stay True for content aimed at children
    "ai_disclosure": False,               # YouTube's synthetic-media label (needed only for realistic content)
    "localize_languages": ["es", "hi", "pt", "fr", "ar", "id", "de", "ja", "ru", "ta", "zh-Hans", "ko"],
    "editions": [],                       # full dubbed editions to render per episode, e.g. ["es", "hi"]
    "edition_channels": {},               # language -> refresh token of a separate channel (empty = main channel)
    "voices": {},                         # character id -> voice override (empty = cast defaults)
    "voice_rate": "-4%",                  # a touch slower than adult narration
    "music": True,
    "music_level": 0.16,                  # bed level under speech (kids content: keep speech dominant)
    "captions_burned": True,              # big friendly sing-along words on screen for songs + key words
    "provider_order": ["gemini", "groq", "nvidia", "cerebras", "openrouter", "mistral", "openai", "anthropic"],
    "quality_bar": 7.5,                   # Child-psychology critic average needed to pass (0-10)
    "max_revisions": 2,
    "llm_daily_budget": 300,
    "kill_switch": False,                 # True = nothing is published
    "max_posts_per_day": 3,               # long episodes; Shorts ride along (upload = 1 quota unit, 100/day bucket)
    "keep_days": 30,
    "series_playlists": True,             # each category becomes a playlist (binge-friendly, kids rewatch)
    "custom_voices": [],                  # (kept for the shared TTS module; uploads are not used for kids)
    "humanize": {"breaths": True, "room_tone": False},
    "render_scale": 1.0,
    "pace": "rapid",                      # calm | lively | rapid | auto (auto = the optimizer learns it from retention)
    "art_style": "auto",                  # auto (learn which look holds kids, per age band) | classic | paper | comic |
                                          # pixel | anime | ps2 | risograph
    "render_3d_quality": "standard",       # 3D cartoon look: draft (540p) | standard (720p) | high (1080p, 24 fps)
    "render_3d_engine": "auto",            # auto (GPU if Blender sees one, else CPU) | cycles | eevee
    "palette": "auto",                    # auto (by category + age, render/palette.py) or a palette id
    # ---- AI animation (render/aivideo.py): code | hero (AI hero shots) | full (every shot AI-animated)
    "animation": "code",
    "ai_video_provider": "auto",          # auto | omni (Gemini Omni Flash) | kling (fal.ai) | runway
    "ai_video_budget_usd": 5,             # per-episode spending cap; shots past it keep the code animation
    "ai_video_hero_shots": 6,
    "optimizer": True,                    # learn pace/length/thumbnail/title styles from YouTube data
    "explore_rate": 0.2,                  # share of episodes that try a non-best option (keeps learning)
    # ---- growth engine (kids/growth.py)
    "growth_cta": True,                   # one parent-directed subscribe line at the end + description + end card
    "cta_line": "Grown-ups, tap subscribe so we can play again soon!",
    "shorts_from_episodes": True,         # every episode's song becomes a vertical Short (discovery)
    "shorts_per_week": 3,                 # Shorts cut from the week's episodes (1-2 each: song first, then a lively bit)
    "book_series": False,                 # automatic book series: next story of a book each day (app/kids/series.py)
    "book_series_per_day": 1,             # how many of the daily episodes come from the book series
    "opening_jingle": False,              # False = open straight on the hook line (no logo/title card at the top)
    "compilation_weekly": True,           # weekly long compilation of the best episodes (watch time)
    "compilation_minutes": 45,
    "compilation_weekday": 5,             # 5 = Saturday (weekend family viewing)                  # 0.667 = 1280x720 render (2.2x faster)
}

_cache: dict = {"t": 0.0, "app": None, "secrets": None}


# ---- secrets at rest: encrypted with a key derived from SECRET_KEY (Fernet = AES-128-CBC + HMAC).
# A database leak alone no longer leaks your API keys. Rotating SECRET_KEY means re-entering keys.
def _fernet():
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    # Salt kept from the old "Kidsmith" name on purpose: changing it would make saved keys unreadable.
    key = hashlib.sha256(("kidsmith-secrets:" + config.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _decode_secrets(stored) -> dict:
    if not stored:
        return {}
    if isinstance(stored, dict) and "_enc" in stored:
        import json
        try:
            return json.loads(_fernet().decrypt(stored["_enc"].encode()))
        except Exception:
            print("[settings] saved keys could not be decrypted (SECRET_KEY changed?) - re-enter them in Settings")
            return {}
    return dict(stored)  # legacy plain dict; encrypted on next save


def _encode_secrets(values: dict) -> dict:
    import json
    return {"_enc": _fernet().encrypt(json.dumps(values).encode()).decode()}


def _load(force: bool = False):
    if force or time.time() - _cache["t"] > 15 or _cache["app"] is None:
        db = get_db()
        stored = db.get_setting("app", {}) or {}
        merged = copy.deepcopy(DEFAULTS)
        for k, v in stored.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        _cache["app"] = merged
        _cache["secrets"] = _decode_secrets(db.get_setting("secrets", {}))
        _cache["t"] = time.time()


def app_settings(force: bool = False) -> dict:
    _load(force)
    return copy.deepcopy(_cache["app"])


def save_app_settings(patch: dict) -> dict:
    db = get_db()
    stored = db.get_setting("app", {}) or {}
    for k, v in patch.items():
        if k in DEFAULTS:
            stored[k] = v
    db.set_setting("app", stored)
    return app_settings(force=True)


def secret(name: str) -> str:
    """Dashboard-saved value first, then environment."""
    _load()
    v = (_cache["secrets"] or {}).get(name)
    return v or os.getenv(name, "").strip()


def save_secrets(values: dict) -> None:
    db = get_db()
    stored = _decode_secrets(db.get_setting("secrets", {}))
    for k, v in values.items():
        if k not in config.SECRET_KEYS:
            continue
        if v is None or v == "":
            stored.pop(k, None)
        elif "•" not in v:  # masked value echoed back -> keep old
            stored[k] = v.strip()
    db.set_setting("secrets", _encode_secrets(stored))
    _load(force=True)


def import_env_secrets() -> list[str]:
    """Copy keys set as server environment variables into the dashboard store,
    so the GitHub worker can read them too. Dashboard values are never overwritten."""
    _load()
    have = _cache["secrets"] or {}
    found = {k: os.getenv(k, "").strip() for k in config.SECRET_KEYS if not have.get(k) and os.getenv(k, "").strip()}
    if found:
        save_secrets(found)
    return sorted(found)


def secrets_status() -> dict:
    _load()
    out = {}
    for k in config.SECRET_KEYS:
        v = secret(k)
        src = "dashboard" if (_cache["secrets"] or {}).get(k) else ("env" if os.getenv(k) else None)
        out[k] = {"set": bool(v), "source": src, "preview": ("••••" + v[-4:]) if len(v) > 12 else ("••••" if v else "")}
    return out
