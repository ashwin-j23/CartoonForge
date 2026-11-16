"""Growth engine: what actually grows a kids channel, as a checklist the dashboard tracks.

Made-for-kids videos get no comments, no bell, no end screens or cards, so growth comes from: being suggested
next to videos kids already watch (consistent series + strong search titles), watch time (long videos and
compilations parents leave playing), Shorts for discovery, playlists for binge sessions, and reaching more
countries with dubbed editions.
"""
from __future__ import annotations

from ..db import get_db
from ..settings import app_settings, secret

# phrases parents actually type (evergreen kids search demand); the writer and metadata lean on these
SEO_KEYWORDS = [
    "nursery rhymes", "kids songs", "counting song", "abc song", "phonics song", "learn colors", "learn shapes",
    "toddler learning video", "preschool learning", "bedtime story for kids", "animal sounds", "learn numbers",
    "educational videos for kids", "songs for toddlers", "kindergarten learning", "dinosaur songs for kids",
    "brush your teeth song", "feelings for kids", "story time for kids", "kids learning videos",
]


def status() -> dict:
    s = app_settings()
    db = get_db()
    eps = db.query("episodes", limit=500)
    pub = [e for e in eps if e.get("status") == "published"]
    kinds = lambda k: [e for e in eps if e.get("kind", "episode") == k]  # noqa: E731
    shorts, comps = kinds("short"), kinds("compilation")
    langs = {e.get("language", "en") for e in eps}
    tips = [
        {"title": "Connect your YouTube channel", "done": bool(secret("YT_REFRESH_TOKEN")),
         "detail": "Channel → Connect YouTube. Uploads are declared made-for-kids automatically."},
        {"title": "Post on a fixed schedule", "done": int(s.get("episodes_per_week", 0)) >= 2,
         "detail": "2-4 long episodes a week on the same days. The algorithm and parents both reward routine."},
        {"title": "One parent-directed subscribe ask per video", "done": bool(s.get("growth_cta")),
         "detail": "End card + one gentle line + description. Subscribe works on made-for-kids videos; comments don't."},
        {"title": "A Short from every episode", "done": bool(s.get("shorts_from_episodes")) and len(shorts) > 0,
         "detail": "The song, vertical, under 60 s. Shorts are the biggest discovery surface for new kids channels."},
        {"title": "Weekly long compilation", "done": bool(s.get("compilation_weekly")) and len(comps) > 0,
         "detail": "30-60 minute compilations get left playing at home: the biggest watch-time driver."},
        {"title": "Series playlists", "done": bool(s.get("series_playlists")),
         "detail": "Every category is a playlist, so one video leads to the next (binge sessions)."},
        {"title": "Titles in parents' search words", "done": True,
         "detail": "Titles lead with phrases like 'Counting Song', 'Learn Colors', 'for Toddlers' (automatic)."},
        {"title": "Translated titles in 10+ languages", "done": len(s.get("localize_languages") or []) >= 8,
         "detail": "Shown to each viewer in their language. Free, one AI call per episode."},
        {"title": "Dubbed editions for big markets", "done": len(langs) > 1 or bool(s.get("editions")),
         "detail": "Spanish, Hindi, Portuguese, Arabic and Indonesian are huge for kids. Start with 1-2 (Channel page)."},
        {"title": "First 10 episodes published", "done": len(pub) >= 10,
         "detail": f"{len(pub)}/10. YouTube needs a library to understand who to suggest you to."},
    ]
    return {"tips": tips, "shorts": shorts[:30], "compilations": comps[:20], "seo_keywords": SEO_KEYWORDS}


# where most views come from -> the zone posting times follow (a representative city per country)
COUNTRY_TZ = {
    "US": "America/New_York", "CA": "America/Toronto", "MX": "America/Mexico_City", "BR": "America/Sao_Paulo",
    "GB": "Europe/London", "IE": "Europe/Dublin", "DE": "Europe/Berlin", "FR": "Europe/Paris", "NL": "Europe/Amsterdam",
    "IN": "Asia/Kolkata", "PK": "Asia/Karachi", "BD": "Asia/Dhaka", "AE": "Asia/Dubai", "SA": "Asia/Riyadh",
    "PH": "Asia/Manila", "ID": "Asia/Jakarta", "MY": "Asia/Kuala_Lumpur", "SG": "Asia/Singapore", "TH": "Asia/Bangkok",
    "AU": "Australia/Sydney", "NZ": "Pacific/Auckland", "NG": "Africa/Lagos", "ZA": "Africa/Johannesburg",
    "KE": "Africa/Nairobi", "EG": "Africa/Cairo",
}
MIN_VIEWS = 300          # don't move the schedule on a handful of views
MIN_SHARE = 0.35         # ...or when no country clearly leads


def pick_timezone(views: dict) -> str | None:
    """The zone of the country that clearly leads the views, or None (not enough data / no clear leader)."""
    total = sum(views.values())
    if total < MIN_VIEWS:
        return None
    top, n = max(views.items(), key=lambda kv: kv[1])
    return COUNTRY_TZ.get(top) if n / total >= MIN_SHARE else None


def tune_timezone() -> str:
    """Daily: follow the audience. Posting times stay the same local hours (breakfast, late morning, after
    school), just in the zone where most children actually watch."""
    from ..publish import youtube
    from ..settings import save_app_settings
    s = app_settings()
    if not s.get("auto_timezone", True):
        return "off"
    views = youtube.audience_countries()
    tz = pick_timezone(views)
    if not tz or tz == s.get("timezone"):
        return f"kept {s.get('timezone')} ({sum(views.values())} views)"
    save_app_settings({"timezone": tz})
    get_db().log(f"Posting times moved to {tz}: most views now come from there", "info")
    return f"moved to {tz}"
