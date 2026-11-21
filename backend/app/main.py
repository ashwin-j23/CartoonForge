"""HTTP API + dashboard host.

Auth: one owner password -> JWT (Bearer header, or ?token= for <img> previews). Public without auth: /api/health,
/api/login, /api/cast/{id}.png, /media/* (videos and thumbnails), the dashboard files, the YouTube OAuth callback.
Heavy work (writing, rendering, publishing) runs on one background worker thread (WORKER_MODE=inline) or on the
GitHub Actions render farm (WORKER_MODE=github).
"""
from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
import io
import queue
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, pipeline
from .db import get_db, now_iso
from .kids import cast, categories, growth, languages, planner, psychology
from .settings import DEFAULTS, app_settings, import_env_secrets, save_app_settings, save_secrets, secrets_status

probs = config.check_security(for_web=True)
if probs and config.IS_PROD and not config.ON_VERCEL:
    raise SystemExit("Refusing to start:\n  - " + "\n  - ".join(probs))
# On Vercel a crash only shows FUNCTION_INVOCATION_FAILED: answer every request with what is missing instead
SETUP_PROBLEMS = probs if (probs and config.ON_VERCEL) else []

@asynccontextmanager
async def lifespan(_app):
    _start()
    yield


app = FastAPI(title="CartoonForge", docs_url=None, redoc_url=None, lifespan=lifespan)
if SETUP_PROBLEMS:
    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def _setup_needed(request: Request, call_next):
        return JSONResponse({"detail": "Setup needed: add these in Vercel → Settings → Environment Variables, then "
                                       "redeploy. " + " ".join(SETUP_PROBLEMS), "setup": SETUP_PROBLEMS}, 503)

if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

# Security headers on every response (HawkScan findings: CSP, anti-clickjacking, nosniff). The same set is in
# vercel.json for the dashboard Vercel serves. Keep the two CSP strings identical.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src"
       " 'self' https://fonts.gstatic.com; img-src 'self' data: blob: https://*.supabase.co https://i.ytimg.com; media-src 'self"
       "' blob: https://*.supabase.co; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = {"Content-Security-Policy": CSP, "X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "strict-origin-when-cross-origin"}


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


# ---------------------------------------------------------------- auth
def _token() -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=config.TOKEN_DAYS)
    return jwt.encode({"sub": "owner", "exp": exp}, config.SECRET_KEY, algorithm="HS256")


def auth(request: Request) -> None:
    h = request.headers.get("authorization", "")
    tok = h[7:] if h.lower().startswith("bearer ") else request.query_params.get("token", "")
    try:
        jwt.decode(tok, config.SECRET_KEY, algorithms=["HS256"])
    except Exception:  # noqa: BLE001
        raise HTTPException(401, "Please sign in") from None


_fails: dict[str, list[float]] = {}


@app.post("/api/login")
def login(body: dict, request: Request):
    ip = request.client.host if request.client else "?"
    recent = [t for t in _fails.get(ip, []) if time.time() - t < 600]
    if len(recent) >= 8:
        raise HTTPException(429, "Too many attempts, wait 10 minutes")
    if not hmac.compare_digest(str(body.get("password", "")), config.ADMIN_PASSWORD):
        _fails[ip] = recent + [time.time()]
        raise HTTPException(401, "Wrong password")
    return {"token": _token()}


@app.get("/api/health")
def health():
    db = get_db()
    try:
        db.get_setting("app")                            # a real read: catches missing tables / bad keys
    except Exception as e:  # noqa: BLE001
        return Response(content=__import__("json").dumps({"ok": False, "db": db.kind, "error": str(e)[:400]}),
                        status_code=503, media_type="application/json")
    return {"ok": True, "db": db.kind}


@app.get("/api/me", dependencies=[Depends(auth)])
def me():
    return {"ok": True}


# ---------------------------------------------------------------- background worker (inline mode)
_jobs: "queue.Queue[tuple]" = queue.Queue()
_busy = {"v": False}


def _worker():
    while True:
        fn, args = _jobs.get()
        _busy["v"] = True
        try:
            fn(*args)
        except Exception as e:  # noqa: BLE001
            get_db().log(f"Background job failed: {e}", "error")
        finally:
            _busy["v"] = False


_last_dispatch: dict = {}


def _dispatch_github(workflow: str = "") -> bool:
    if not (config.GITHUB_REPO and config.GITHUB_TOKEN):
        _last_dispatch["status"] = "no GITHUB_TOKEN" if config.GITHUB_REPO else "no GITHUB_REPO"
        return False
    wf = workflow or config.GITHUB_WORKFLOW
    r = httpx.post(f"https://api.github.com/repos/{config.GITHUB_REPO}/actions/workflows/{wf}/dispatches",
                   headers={"Authorization": f"Bearer {config.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
                   json={"ref": config.GITHUB_REF}, timeout=20)
    _last_dispatch["status"] = r.status_code
    if r.status_code >= 300:
        try:
            _last_dispatch["status"] = f"{r.status_code}: {str(r.json().get('message', ''))[:120]}"
        except ValueError:
            pass
    return r.status_code < 300


HEAVY_ON_VERCEL = "On Vercel, writing and rendering run on the GitHub render farm"


def run(fn, *args) -> bool:
    """Queue heavy work. In github mode, writing/rendering goes to the render farm instead.
    On Vercel nothing heavy ever runs in-process (no voices, 5-minute limit): if the render farm can't be started
    right now, the work stays queued for its next scheduled run. Returns True if the work was started/queued here."""
    if config.WORKER_MODE == "github" and fn in (pipeline.process, pipeline.tick, pipeline.publish):
        if _dispatch_github():
            return True
    if config.ON_VERCEL:
        get_db().log(f"{HEAVY_ON_VERCEL}; it couldn't be started now (is GITHUB_TOKEN set on Vercel?). "
                     "Queued for its next scheduled run (every 6 hours).", "warn")
        return False
    _jobs.put((fn, args))
    return True


def _scheduler():
    while True:
        time.sleep(300)
        try:
            if config.WORKER_MODE == "github":
                pipeline.publish_due()
            elif not _busy["v"] and _jobs.empty():
                from . import automation
                _jobs.put((lambda: automation.record_tick(*_timed(pipeline.tick, True, 1800)), ()))
        except Exception as e:  # noqa: BLE001
            print("[scheduler]", e)


def _timed(fn, *a):
    t = time.time()
    return fn(*a), time.time() - t


def _start():
    try:
        import_env_secrets()
    except Exception as e:  # noqa: BLE001
        print("[startup] could not import env keys:", e)
    try:                                   # the worker (GitHub) needs the site address for feedback links
        if config.ON_VERCEL and config.PUBLIC_BASE_URL and app_settings().get("site_url") != config.PUBLIC_BASE_URL:
            save_app_settings({"site_url": config.PUBLIC_BASE_URL})
    except Exception as e:  # noqa: BLE001
        print("[startup] could not save site_url:", e)
    threading.Thread(target=_worker, daemon=True).start()
    if config.INTERNAL_SCHEDULER == "1":
        threading.Thread(target=_scheduler, daemon=True).start()
    if not config.IS_PROD:
        print(f"\n  CartoonForge  →  http://localhost:8000   password: {config.ADMIN_PASSWORD}\n", flush=True)


# ---------------------------------------------------------------- episodes
def _summary(e: dict) -> dict:
    m = e.get("meta") or {}
    return {k: e.get(k) for k in ("id", "created_at", "status", "category", "topic", "age_band", "language", "duration",
                                   "thumb_url", "video_url", "publish_at", "published_at", "youtube", "progress", "error", "kind",
                                   "parent_id", "edition_of", "art_style", "animation", "rendered_style", "palette", "rendered_palette")} | {
        "title": m.get("title") or e.get("topic"), "score": (e.get("critic") or {}).get("score"),
        "kind": e.get("kind", "episode"), "views": (e.get("stats") or {}).get("views"),
        "likes": (e.get("stats") or {}).get("likes")}


def _get(eid: str) -> dict:
    e = get_db().get("episodes", eid)
    if not e:
        raise HTTPException(404, "Episode not found")
    return e


def _full(e: dict) -> dict:
    e = dict(e)
    e["log"] = get_db().query("events", eq={"episode_id": e["id"]}, limit=80)
    e.setdefault("kind", "episode")
    e.setdefault("editions", {})
    return e


@app.get("/api/episodes", dependencies=[Depends(auth)])
def list_episodes(status: str | None = None, kind: str | None = None):
    rows = get_db().query("episodes", eq={"status": status} if status else None, limit=300, light=True)
    if kind:
        rows = [r for r in rows if r.get("kind", "episode") == kind]
    return [_summary(r) for r in rows]


@app.get("/api/episodes/{eid}", dependencies=[Depends(auth)])
def get_episode(eid: str):
    return _full(_get(eid))


@app.post("/api/episodes", dependencies=[Depends(auth)])
def new_episode(body: dict):
    cat = body.get("category") or None
    if cat and cat not in categories.BY_ID:
        raise HTTPException(400, "Unknown category")
    band = body.get("age_band") or None
    if band and band not in psychology.AGE_BANDS:
        raise HTTPException(400, "Unknown age band")
    mins = body.get("minutes")
    if mins is not None and not 5 <= float(mins) <= 20:
        raise HTTPException(400, "Minutes must be 5-20")
    source = None
    if isinstance(body.get("book"), dict):
        from .kids import books
        try:
            source = books.story(int(body["book"]["gid"]), int(body["book"].get("index", 0)))
        except (ValueError, KeyError, TypeError) as ex:
            raise HTTPException(400, f"Book story: {ex}") from None
        except httpx.HTTPError as ex:
            raise HTTPException(502, f"Could not reach Project Gutenberg: {ex}") from None
    style, anim, budget = _look(body)
    ep = pipeline.create(cat, (body.get("topic") or "").strip()[:120] or None, band, mins, source=source,
                         art_style=style, animation=anim, ai_budget_usd=budget, palette=_palette_arg(body))
    run(pipeline.process, ep["id"])
    return _full(ep)


def _look(body: dict) -> tuple[str | None, str | None, float | None]:
    from .render.styles import STYLES
    style = body.get("art_style") or None
    if style and style != "auto" and style not in STYLES:
        raise HTTPException(400, "Unknown art style")
    anim = body.get("animation") or None
    if anim and anim not in ("code", "hero", "full"):
        raise HTTPException(400, "animation must be code, hero or full")
    budget = body.get("ai_budget_usd")
    if budget is not None:
        try:
            budget = max(0.0, min(1000.0, float(budget)))
        except (TypeError, ValueError):
            raise HTTPException(400, "ai_budget_usd must be a number") from None
    return style, anim, budget


def _palette_arg(body: dict) -> str | None:
    from .render.palette import PALETTES
    p = body.get("palette") or None
    if p and p != "auto" and p not in PALETTES:
        raise HTTPException(400, "Unknown palette")
    return p


@app.post("/api/episodes/{eid}/restyle", dependencies=[Depends(auth)])
def restyle(eid: str, body: dict):
    """Re-render an episode in another look and/or animation mode (the script stays)."""
    e = _get(eid)
    if not e.get("script"):
        raise HTTPException(400, "No script yet")
    if e["status"] in pipeline.ACTIVE:
        raise HTTPException(409, "Busy — wait for the current step")
    style, anim, budget = _look(body)
    patch = {"status": "scripted", "progress": {"stage": "queued", "pct": 0}}
    if style:
        patch["art_style"] = style
    if anim:
        patch["animation"] = anim
    if budget is not None:
        patch["ai_budget_usd"] = budget
    pal = _palette_arg(body)
    if pal:
        patch["palette"] = pal
    e = get_db().update("episodes", eid, patch)
    get_db().log(f"Re-rendering in {style or e.get('art_style', 'auto')} / {anim or e.get('animation', 'code')}", episode_id=eid)
    run(pipeline.process, eid)
    return _full(e)


@app.patch("/api/episodes/{eid}", dependencies=[Depends(auth)])
def patch_episode(eid: str, body: dict):
    e = _get(eid)
    patch = {}
    if isinstance(body.get("meta"), dict):
        m = dict(e.get("meta") or {})
        for k in ("title", "description", "tags"):
            if k in body["meta"]:
                m[k] = body["meta"][k]
        m["title"] = str(m.get("title", ""))[:100]
        patch["meta"] = m
    if isinstance(body.get("script"), dict) and body["script"].get("segments"):
        from .kids import safety
        patch["script"] = body["script"]
        patch["safety"] = safety.check_episode({"script": body["script"], "meta": patch.get("meta") or e.get("meta") or {}})
    if "publish_at" in body:
        patch["publish_at"] = body["publish_at"]
    return _full(get_db().update("episodes", eid, patch)) if patch else _full(e)


@app.post("/api/episodes/{eid}/approve", dependencies=[Depends(auth)])
def approve(eid: str, body: dict | None = None):
    e = _get(eid)
    if e["status"] in ("scripted", "failed") and not e.get("video_url"):
        raise HTTPException(400, "Render the episode first")
    try:
        return _full(pipeline.approve(eid, (body or {}).get("publish_at")))
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None


@app.post("/api/episodes/{eid}/reject", dependencies=[Depends(auth)])
def reject(eid: str):
    _get(eid)
    return _full(get_db().update("episodes", eid, {"status": "rejected", "publish_at": None}))


@app.post("/api/episodes/{eid}/rewrite", dependencies=[Depends(auth)])
def rewrite(eid: str):
    e = _get(eid)
    if e["status"] in pipeline.ACTIVE:
        raise HTTPException(409, "Busy — wait for the current step")
    e = get_db().update("episodes", eid, {"status": "planned", "progress": {"stage": "queued", "pct": 0}})
    run(pipeline.process, eid)
    return _full(e)


@app.post("/api/episodes/{eid}/render", dependencies=[Depends(auth)])
def rerender(eid: str):
    e = _get(eid)
    if not e.get("script"):
        raise HTTPException(400, "No script yet")
    if e["status"] in pipeline.ACTIVE:
        raise HTTPException(409, "Busy — wait for the current step")
    e = get_db().update("episodes", eid, {"status": "scripted", "progress": {"stage": "queued", "pct": 0}})
    run(pipeline.process, eid)
    return _full(e)


@app.post("/api/episodes/{eid}/publish", dependencies=[Depends(auth)])
def publish_now(eid: str):
    e = _get(eid)
    if not e.get("video_url"):
        raise HTTPException(400, "Nothing rendered yet")
    if e["status"] not in ("review", "approved"):
        raise HTTPException(400, f"Can't publish from '{e['status']}'")
    get_db().update("episodes", eid, {"status": "approved", "publish_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    run(pipeline.publish, eid)
    return _full(_get(eid))


@app.post("/api/episodes/{eid}/edition", dependencies=[Depends(auth)])
def edition(eid: str, body: dict):
    lang = body.get("lang")
    if lang not in languages.LANGS:
        raise HTTPException(400, "Unknown language")
    try:
        ed = pipeline.make_edition(eid, lang)
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None
    run(pipeline.process, ed["id"])
    return _full(_get(eid))


@app.post("/api/episodes/{eid}/short", dependencies=[Depends(auth)])
def short(eid: str):
    e = _get(eid)
    if not e.get("video_url"):
        raise HTTPException(400, "Render the episode first")
    try:
        return _full(pipeline.make_short(eid))
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(400, str(ex)) from None


@app.delete("/api/episodes/{eid}", dependencies=[Depends(auth)])
def delete_episode(eid: str):
    from . import storage
    e = _get(eid)
    keys = [u.split(f"/{config.SUPABASE_BUCKET}/", 1)[-1] if config.SUPABASE_URL else u.split("/media/", 1)[-1]
            for u in (e.get("video_url"), e.get("thumb_url")) if u and e.get("kind") != "short"]
    try:
        storage.remove([k for k in keys if k])
    except Exception:  # noqa: BLE001
        pass
    get_db().delete("episodes", eid)
    return {"ok": True}


@app.get("/api/episodes/{eid}/preview.png", dependencies=[Depends(auth)])
def preview(eid: str, t: float = 5.0):
    from .render.episode import preview as pv
    e = _get(eid)
    if not e.get("script"):
        raise HTTPException(404, "No script yet")
    img = pv(e["script"], {**app_settings()}, t).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=60"})


# ---------------------------------------------------------------- reference data
@app.get("/api/categories", dependencies=[Depends(auth)])
def get_categories():
    return categories.CATEGORIES


@app.get("/api/cast", dependencies=[Depends(auth)])
def get_cast():
    return [{"id": k, **{f: v[f] for f in ("name", "species", "role", "look", "personality", "catchphrase", "voice")},
             "colors": {n: "#%02x%02x%02x" % c for n, c in v["colors"].items()}} for k, v in cast.CAST.items()]


# ---------------------------------------------------------------- characters (story cast library)
@app.get("/api/characters", dependencies=[Depends(auth)])
def characters_list(tier: str | None = None, q: str = ""):
    from .kids import library
    return library.all_chars(tier if tier in library.TIERS else None, q.strip()[:60])


@app.post("/api/characters/from-story", dependencies=[Depends(auth)])
def characters_from_story(body: dict):
    from .kids import library
    title = str(body.get("title") or "").strip()[:160]
    text = str(body.get("text") or "").strip()
    if not title and not text:
        raise HTTPException(400, "Give the story a title or paste its text")
    res = library.design_from_story(title or text[:60], text[:20000], str(body.get("book") or "")[:120])
    get_db().log(f"Designed characters for '{title or 'a story'}': {res['created']} new, {res['reused']} reused")
    return res


@app.get("/api/characters/{cid}", dependencies=[Depends(auth)])
def character_get(cid: str):
    from .kids import library
    c = library.get(cid)
    if not c:
        raise HTTPException(404, "Unknown character")
    eps = []
    for eid in (c.get("episodes") or [])[-30:]:
        e = get_db().get("episodes", eid)
        if e:
            eps.append({"id": eid, "title": (e.get("meta") or {}).get("title") or e.get("topic"), "status": e["status"]})
    return {**c, "episodes_detail": eps}


@app.post("/api/characters", dependencies=[Depends(auth)])
def character_create(body: dict):
    from .kids import library
    try:
        return library.create(body, {"type": "custom"}, body.get("tier") if body.get("tier") in library.TIERS else "recurring")
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None


@app.patch("/api/characters/{cid}", dependencies=[Depends(auth)])
def character_patch(cid: str, body: dict):
    from .kids import library
    try:
        return library.update(cid, body)
    except KeyError:
        raise HTTPException(404, "Unknown character") from None


@app.delete("/api/characters/{cid}", dependencies=[Depends(auth)])
def character_delete(cid: str):
    from .kids import library
    try:
        library.delete(cid)
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None
    return {"ok": True}


@app.get("/api/cast/{cid}.png")
def cast_png(cid: str, emotion: str = "happy", arms: str = "down", size: int = 360, style: str = ""):
    from .render.characters import GUESTS, register_guests, sprite
    from .render.styles import STYLES, set_style
    if cid not in cast.CAST:
        from .kids import library
        row = get_db().get("characters", cid)
        if row:
            register_guests({"characters": [library.spec(row)]})
    if cid not in cast.CAST and cid not in GUESTS:
        # a story character: find the most recent episode that designed it
        for e in get_db().query("episodes", limit=60):
            if any(g.get("id") == cid for g in (e.get("script") or {}).get("characters") or []):
                register_guests(e["script"])
                break
    if cid not in cast.CAST and cid not in GUESTS:
        raise HTTPException(404, "Unknown character")
    buf = io.BytesIO()
    with _style_lock:
        set_style(style if style in STYLES else "classic")
        try:
            sprite(cid, max(64, min(720, size)), 0, "open", emotion, arms).save(buf, "PNG")
        finally:
            set_style("classic")
    # short cache: library characters can be edited
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=300"})


_style_lock = threading.Lock()


@app.get("/api/psychology", dependencies=[Depends(auth)])
def get_psychology():
    return {"bands": psychology.AGE_BANDS, "principles": psychology.PRINCIPLES, "never": psychology.NEVER,
            "segment_kinds": categories.SEGMENT_KINDS, "paces": psychology.PACES, "styles": _styles()}


def _styles():
    from .render.styles import STYLES
    return STYLES


STYLE_AGES = {"toddler": "1-3", "preschool": "3-5", "early": "5-8", "big": "8-12"}


@app.get("/api/styles", dependencies=[Depends(auth)])
def styles_list():
    from .render.aivideo import STYLE_WORDS
    from .render.styles import STYLES
    out = []
    for k, v in STYLES.items():
        ages = [STYLE_AGES[b] for b in v["bands"] if b in STYLE_AGES]
        best = f"Ages {ages[0].split('-')[0]}-{ages[-1].split('-')[1]}" if ages else ""
        out.append({"id": k, **v, "preview_url": f"/api/styles/{k}.png", "best_for": best,
                    "ai_words": STYLE_WORDS.get(k, "")})
    return out


@app.get("/api/palettes", dependencies=[Depends(auth)])
def palettes_list():
    """Research-based colour palettes (Filmora kids palettes + Straits Times measured real-show palettes)."""
    from .render import palette
    return {"palettes": palette.catalog(), "by_category": palette.FOR_CATEGORY, "vivid_cap": palette.VIVID_CAP,
            "sources": [{"name": palette.FILMORA, "url": "https://filmora.wondershare.com/video-creative-tips/kids-color-palette.html"},
                        {"name": palette.ST, "url": "https://www.straitstimes.com/multimedia/graphics/2026/03/screen-time-kids-video-analysis/index.html"}]}


@app.get("/api/styles/{style}.png")
def style_preview(style: str):
    """A sample frame of a look (cached), for the Settings picker. No auth: it shows only the stock cast."""
    from .render.styles import STYLES
    if style not in STYLES:
        raise HTTPException(404, "Unknown style")
    f = config.DATA_DIR / "style_previews" / f"{style}.jpg"
    if not f.exists() and style == "toy3d":
        from .render import three_d
        if three_d.available():
            from .kids.writer import template_script
            f.parent.mkdir(parents=True, exist_ok=True)
            s = template_script("numbers", "Counting with Hoppy", "preschool", 6, seed=2)
            png = three_d.preview_still(s, {"channel_name": app_settings().get("channel_name", ""), "art_style": style,
                                            "pace": "calm"}, 33.0, f.with_suffix(".png"))
            from PIL import Image as _I
            _I.open(png).convert("RGB").save(f, "JPEG", quality=85)
            png.unlink(missing_ok=True)
    if not f.exists():
        from .kids.writer import template_script
        from .render.episode import preview as pv
        f.parent.mkdir(parents=True, exist_ok=True)
        s = template_script("numbers", "Counting with Pip", "preschool", 6, seed=2)
        pv(s, {"channel_name": app_settings().get("channel_name", ""), "art_style": style, "pace": "calm"}, 33.0,
           scale=.4).convert("RGB").save(f, "JPEG", quality=85)
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


# ---------------------------------------------------------------- books (public domain → episodes)
@app.get("/api/books", dependencies=[Depends(auth)])
def books_shelf():
    from .kids import books
    try:
        return books.shelf()
    except httpx.HTTPError as ex:
        raise HTTPException(502, f"Could not reach Project Gutenberg: {ex}") from None


@app.get("/api/books/search", dependencies=[Depends(auth)])
def books_search(q: str, children: bool = False):
    from .kids import books
    if len(q.strip()) < 2:
        raise HTTPException(400, "Type at least 2 letters")
    try:
        return books.search(q.strip()[:80], children)
    except httpx.HTTPError as ex:
        raise HTTPException(502, f"Could not reach Project Gutenberg: {ex}") from None


@app.get("/api/books/{gid}/stories", dependencies=[Depends(auth)])
def books_stories(gid: int):
    from .kids import books
    try:
        b = books.book(gid)
        items = books.stories(books.text(gid))
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None
    except httpx.HTTPError as ex:
        raise HTTPException(502, f"Could not reach Project Gutenberg: {ex}") from None
    return {"book": b, "stories": [{k: v for k, v in st.items() if k != "text"} for st in items]}


@app.get("/api/books/series", dependencies=[Depends(auth)])
def book_series_status():
    from .kids import series
    return series.status()


@app.put("/api/books/series", dependencies=[Depends(auth)])
def book_series_update(body: dict):
    from .kids import series
    patch = {}
    if "enabled" in body:
        patch["book_series"] = bool(body["enabled"])
    if "per_day" in body:
        try:
            patch["book_series_per_day"] = max(1, min(10, int(body["per_day"])))
        except (TypeError, ValueError):
            raise HTTPException(400, "per_day must be a number") from None
    if patch:
        save_app_settings(patch)
    try:
        if body.get("gid"):
            series.choose(int(body["gid"]), int(body.get("start", 0)))
        elif patch.get("book_series") and not series.status()["book"]:
            series._ensure_book({})                      # first switch-on: pick the first shelf book now
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None
    except httpx.HTTPError as ex:
        raise HTTPException(502, f"Could not reach Project Gutenberg: {ex}") from None
    if "enabled" in body:
        get_db().log("Book series " + ("ON: the next story of the book becomes an episode each day"
                                       if body["enabled"] else "OFF"))
    return series.status()


@app.post("/api/books/series/skip", dependencies=[Depends(auth)])
def book_series_skip(body: dict | None = None):
    from .kids import series
    try:
        series.skip(int((body or {}).get("n", 1)))
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None
    return series.status()


@app.post("/api/books/series/restart", dependencies=[Depends(auth)])
def book_series_restart():
    from .kids import series
    try:
        series.restart()
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None
    return series.status()


# ---------------------------------------------------------------- parent / viewer feedback
_fb_hits: dict[str, list[float]] = {}


@app.get("/api/public/episode/{eid}")
def public_episode(eid: str):
    """What the public feedback form shows about a video: only published episodes, only public fields."""
    e = get_db().get("episodes", eid[:20])
    if not e or e.get("status") != "published":
        raise HTTPException(404, "Episode not found")
    yt = e.get("youtube") or {}
    return {"id": e["id"], "title": (e.get("meta") or {}).get("title") or e.get("topic"), "thumb_url": e.get("thumb_url"),
            "youtube_url": yt.get("url") if isinstance(yt, dict) else None,
            "channel": app_settings().get("channel_name")}


@app.post("/api/public/feedback")
def submit_feedback(body: dict, request: Request):
    """Public: grown-ups' feedback on an episode. Rate-limited, honeypot, nothing personal stored."""
    from .kids import feedback
    if (body or {}).get("website"):                  # honeypot: bots fill every field
        return {"ok": True}
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")
    recent = [x for x in _fb_hits.get(ip, []) if time.time() - x < 600]
    if len(recent) >= 5:
        raise HTTPException(429, "Thanks! You've sent a lot of feedback already, please try again later.")
    try:
        row = feedback.clean(body)
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None
    if row.get("episode_id"):
        e = get_db().get("episodes", row["episode_id"])
        if not e or e.get("status") != "published":
            row["episode_id"] = None
    _fb_hits[ip] = recent + [time.time()]
    feedback.save(row)
    return {"ok": True}


@app.get("/api/feedback", dependencies=[Depends(auth)])
def feedback_list():
    from .kids import feedback
    items = feedback.rows()
    titles = {e["id"]: (e.get("meta") or {}).get("title") or e.get("topic")
              for e in get_db().query("episodes", eq={"status": "published"}, limit=300)}
    return {"summary": feedback.summary(items), "items": [{**r, "episode_title": titles.get(r.get("episode_id"))}
                                                          for r in items[:200]],
            "form_url": feedback.site_url() + "/#/feedback" if feedback.site_url() else None}


@app.post("/api/feedback/ai", dependencies=[Depends(auth)])
def feedback_ai():
    from .kids import feedback
    from .llm.router import LLMError
    items = feedback.rows()
    if not items:
        raise HTTPException(400, "No feedback yet")
    try:
        return feedback.ai_summary(items)
    except (LLMError, ValueError) as ex:
        raise HTTPException(503, f"AI summary unavailable right now: {str(ex)[:160]}") from None


@app.post("/api/feedback/make", dependencies=[Depends(auth)])
def feedback_make(body: dict):
    """Turn a topic parents asked for into an episode."""
    topic = " ".join(str((body or {}).get("topic") or "").split())[:120]
    if len(topic) < 3:
        raise HTTPException(400, "Topic too short")
    ep = pipeline.create(None, topic, None, None, why="Requested by parents (feedback)")
    get_db().update("episodes", ep["id"], {"why": "Requested by parents (feedback)"})
    run(pipeline.process, ep["id"])
    return _full(get_db().get("episodes", ep["id"]))


@app.get("/api/optimizer", dependencies=[Depends(auth)])
def get_optimizer():
    from .kids import optimizer
    return optimizer.summary()


@app.get("/api/languages", dependencies=[Depends(auth)])
def get_languages():
    return languages.catalog()


@app.get("/api/voices", dependencies=[Depends(auth)])
def get_voices():
    from . import tts
    return tts.catalog()


@app.get("/api/llm", dependencies=[Depends(auth)])
def get_llm():
    from .llm import router
    return router.available()


# ---------------------------------------------------------------- AI animation
@app.get("/api/aivideo", dependencies=[Depends(auth)])
def aivideo_info():
    from .render import aivideo
    return aivideo.catalog(app_settings())


@app.get("/api/aivideo/estimate", dependencies=[Depends(auth)])
def aivideo_estimate(mode: str = "hero", minutes: float = 12, provider: str = ""):
    from .render import aivideo
    s = app_settings()
    if mode not in ("code", "hero", "full"):
        raise HTTPException(400, "mode must be code, hero or full")
    prov = provider if provider in aivideo.PROVIDERS else (aivideo.active(s) or aivideo.ORDER[0])
    return {**aivideo.estimate(mode, max(1.0, min(30.0, minutes)), prov, int(s.get("ai_video_hero_shots", 6))),
            "provider": prov, "configured": prov in aivideo.configured()}


# ---------------------------------------------------------------- deploy readiness
@app.get("/api/deploy", dependencies=[Depends(auth)])
def deploy_info():
    import os
    from .settings import secret
    target = "vercel" if os.getenv("VERCEL") else ("docker" if os.path.exists("/.dockerenv") else "local")
    supa = bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY)
    gh = bool(config.GITHUB_REPO and config.GITHUB_TOKEN)
    checklist = [
        {"title": "Supabase database + storage", "done": supa,
         "detail": "Vercel has no disk: set SUPABASE_URL, SUPABASE_SERVICE_KEY and run docs/supabase.sql once."},
        {"title": "GitHub Actions render farm", "done": gh and config.WORKER_MODE == "github",
         "detail": "WORKER_MODE=github, GITHUB_REPO, GITHUB_TOKEN; add the same secrets to the GitHub repo."},
        {"title": "Strong ADMIN_PASSWORD and SECRET_KEY", "done": not config.check_security(True),
         "detail": "Set both as Vercel environment variables (SECRET_KEY must match the GitHub secret)."},
        {"title": "CRON_SECRET for scheduled publishing", "done": bool(config.CRON_SECRET),
         "detail": "Vercel Cron calls /api/cron/tick with it (vercel.json)."},
        {"title": "PUBLIC_BASE_URL", "done": bool(config.PUBLIC_BASE_URL),
         "detail": "Your Vercel URL, for the YouTube OAuth redirect."},
        {"title": "An AI key", "done": pipeline.has_ai(), "detail": "Gemini or Groq (free) for writing."},
        {"title": "YouTube connected", "done": bool(secret("YT_CLIENT_ID") and secret("YT_CLIENT_SECRET") and secret("YT_REFRESH_TOKEN")),
         "detail": "Client ID + secret in Keys, then Channel → Connect."},
    ]
    return {"target": target, "db": get_db().kind, "worker": config.WORKER_MODE, "checklist": checklist,
            "guide": "docs/DEPLOY-VERCEL.md"}


# ---------------------------------------------------------------- overview / calendar / analytics / growth
@app.get("/api/overview", dependencies=[Depends(auth)])
def overview():
    from .settings import secret
    from concurrent.futures import ThreadPoolExecutor
    db = get_db()
    with ThreadPoolExecutor(3) as ex:                     # independent reads at once: one round trip, not three
        f_rows = ex.submit(db.query, "episodes", limit=500, light=True)
        f_ch = ex.submit(db.get_setting, "channel_cache")
        f_s = ex.submit(app_settings)
        rows, ch, s = f_rows.result(), f_ch.result(), f_s.result()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    nxt = sorted([r for r in rows if r["status"] == "approved" and r.get("publish_at")], key=lambda r: r["publish_at"])
    channel = None
    if secret("YT_REFRESH_TOKEN"):
        if not ch or time.time() - ch.get("t", 0) > 3600:
            try:
                from .publish import youtube
                ch = {**youtube.channel_info(), "t": time.time()}
                db.set_setting("channel_cache", ch)
            except Exception as e:  # noqa: BLE001
                ch = {"error": str(e)[:200]}
        channel = {"connected": "id" in ch, **{k: v for k, v in ch.items() if k != "t"}}
    cur = pipeline.current()
    return {"counts": counts,
            "next_publish": {"id": nxt[0]["id"], "title": (nxt[0].get("meta") or {}).get("title", nxt[0]["topic"]),
                             "publish_at": nxt[0]["publish_at"]} if nxt else None,
            "channel": channel, "warnings": pipeline.overview_warnings(),
            "worker": {"mode": config.WORKER_MODE, "busy": _busy["v"] or bool(cur), "current": cur or None},
            "settings_summary": {k: s.get(k) for k in ("channel_name", "age_band", "target_minutes", "episodes_per_week", "autopilot")}}


def _sched_state(r: dict, now: str) -> tuple[str, str]:
    """(state, go-live time). live = public on YouTube; uploaded = on YouTube, goes public by itself at the time;
    uploading = being sent now; waiting = not uploaded yet (it is uploaded up to 12 h before its time);
    late = its time passed or the last upload attempt failed."""
    yt = r.get("youtube") or {}
    if r["status"] == "published":
        at = yt.get("scheduled_for") or r.get("published_at") or ""
        at = at.replace("Z", "+00:00")
        return ("uploaded" if at > now else "live"), at
    at = r.get("publish_at") or ""
    if r["status"] == "publishing":
        return "uploading", at
    return ("late" if (r.get("error") or (at and at < now)) else "waiting"), at


@app.get("/api/storage", dependencies=[Depends(auth)])
def storage_usage():
    from . import janitor
    return {**janitor.usage(), "plan": janitor.cleanup(dry=True)}


@app.post("/api/storage/cleanup", dependencies=[Depends(auth)])
def storage_cleanup():
    from . import janitor
    return janitor.cleanup()


@app.get("/api/calendar", dependencies=[Depends(auth)])
def calendar():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = get_db().query("episodes", in_={"status": ["approved", "publishing", "published"]}, limit=300, light=True)
    sched = []
    for r in rows:
        state, at = _sched_state(r, now)
        if at:
            sched.append({"id": r["id"], "title": (r.get("meta") or {}).get("title", r["topic"]), "status": r["status"],
                          "state": state, "publish_at": at, "kind": r.get("kind", "episode"),
                          "url": (r.get("youtube") or {}).get("url"), "thumb_url": r.get("thumb_url"),
                          "duration": r.get("duration"), "category": r.get("category"),
                          "views": (r.get("stats") or {}).get("views"),
                          "error": (r.get("error") or "")[:200] if state == "late" else ""})
    live = [x for x in sched if x["state"] == "live"]
    totals = {"episodes": sum(1 for x in live if x["kind"] != "short"), "shorts": sum(1 for x in live if x["kind"] == "short"),
              "uploaded": sum(1 for x in sched if x["state"] == "uploaded"),
              "waiting": sum(1 for x in sched if x["state"] in ("waiting", "uploading", "late"))}
    return {"scheduled": sched, "world_days": planner.upcoming(60), "slots": pipeline.free_slots(8), "now": now,
            "totals": totals, "storage": get_db().get_setting("storage_usage")}


@app.get("/api/analytics", dependencies=[Depends(auth)])
def analytics():
    rows = get_db().query("episodes", eq={"status": "published"}, limit=500, light=True)
    eps, per = [], {}
    tv = tl = 0
    for r in rows:
        st = r.get("stats") or {}
        tv += st.get("views", 0)
        tl += st.get("likes", 0)
        eps.append({"id": r["id"], "title": (r.get("meta") or {}).get("title", r.get("topic")), "category": r.get("category"),
                    "kind": r.get("kind", "episode"), "views": st.get("views", 0), "likes": st.get("likes", 0),
                    "avg_pct": st.get("avg_pct"), "published_at": r.get("published_at"),
                    "url": (r.get("youtube") or {}).get("url")})
        c = per.setdefault(r.get("category") or "other", {"episodes": 0, "views": 0, "pct": []})
        c["episodes"] += 1
        c["views"] += st.get("views", 0)
        if st.get("avg_pct") is not None:
            c["pct"].append(st["avg_pct"])
    cats = [{"id": k, "name": categories.get(k)["name"], "emoji": categories.get(k)["emoji"], "episodes": v["episodes"],
             "views": v["views"], "avg_pct": round(sum(v["pct"]) / len(v["pct"]), 1) if v["pct"] else None}
            for k, v in per.items()]
    return {"totals": {"views": tv, "likes": tl, "episodes": len(rows)},
            "categories": sorted(cats, key=lambda c: -c["views"]),
            "episodes": sorted(eps, key=lambda e: -e["views"])[:100]}


@app.get("/api/growth", dependencies=[Depends(auth)])
def get_growth():
    g = growth.status()
    s = app_settings()
    now = datetime.now(timezone.utc)
    days = (int(s.get("compilation_weekday", 5)) - now.weekday()) % 7
    return {**g, "shorts": [_summary(e) for e in g["shorts"]], "compilations": [_summary(e) for e in g["compilations"]],
            "next_compilation": (now + timedelta(days=days)).date().isoformat() if s.get("compilation_weekly") else None}


@app.post("/api/growth/compilation", dependencies=[Depends(auth)])
def compilation_now():
    try:
        return _full(pipeline.make_compilation())
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None


# ---------------------------------------------------------------- trends
@app.get("/api/trends", dependencies=[Depends(auth)])
def get_trends():
    from .settings import secret
    db = get_db()
    ideas = db.query("trends", order="score", desc=True, limit=60)
    snap = db.get_setting("trends_snapshot") or {}
    return {"ideas": ideas, "snapshot": snap, "has_youtube_key": bool(secret("YOUTUBE_API_KEY")),
            "scanning": bool(_scan_state.get("running"))}


_scan_state: dict = {}


@app.post("/api/trends/scan", dependencies=[Depends(auth)])
def trends_scan():
    """Runs in the background (takes ~1-2 minutes: Wikipedia is polite-rate-limited)."""
    from .kids import trends
    if _scan_state.get("running"):
        return {"started": False, "detail": "A scan is already running"}

    def job():
        _scan_state["running"] = True
        try:
            trends.scan(lambda m: get_db().log(m))
        finally:
            _scan_state["running"] = False
    threading.Thread(target=job, daemon=True).start()
    return {"started": True}


@app.post("/api/trends/{tid}/make", dependencies=[Depends(auth)])
def trend_make(tid: str):
    from .kids import trends
    t = get_db().get("trends", tid)
    if not t:
        raise HTTPException(404, "Trend not found")
    ep = pipeline.create(t["category"], t["topic"], t.get("age_band"), None, why=f"Trending ({t.get('score')}): {t.get('why', '')}")
    get_db().update("episodes", ep["id"], {"angle": t.get("angle", ""), "why": f"Trending ({t.get('score')}): {t.get('why', '')}"[:200]})
    trends.mark_used(tid, ep["id"])
    run(pipeline.process, ep["id"])
    return _full(get_db().get("episodes", ep["id"]))


# ---------------------------------------------------------------- settings / keys / events / tick
@app.get("/api/settings", dependencies=[Depends(auth)])
def get_settings():
    return app_settings()


@app.put("/api/settings", dependencies=[Depends(auth)])
def put_settings(body: dict):
    clean = {k: v for k, v in body.items() if k in DEFAULTS}
    if "target_minutes" in clean:
        clean["target_minutes"] = max(5, min(15, float(clean["target_minutes"])))
    if "pace" in clean and clean["pace"] not in (*psychology.PACES, "auto"):
        raise HTTPException(400, "pace must be calm, lively, rapid or auto")
    if "palette" in clean and clean["palette"] != "auto":
        from .render.palette import PALETTES
        if clean["palette"] not in PALETTES:
            raise HTTPException(400, "Unknown palette")
    if "animation" in clean and clean["animation"] not in ("code", "hero", "full"):
        raise HTTPException(400, "animation must be code, hero or full")
    if "ai_video_provider" in clean and clean["ai_video_provider"] not in ("auto", "omni", "kling", "runway"):
        raise HTTPException(400, "Unknown AI video provider")
    for k, lo, hi in (("ai_video_budget_usd", 0, 1000), ("ai_video_hero_shots", 1, 12)):
        if k in clean:
            try:
                clean[k] = max(lo, min(hi, float(clean[k]) if k.endswith("usd") else int(clean[k])))
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k} must be a number") from None
    clean.pop("made_for_kids", None)          # locked on: content for children must be declared (COPPA)
    return save_app_settings(clean)


@app.get("/api/keys", dependencies=[Depends(auth)])
def get_keys():
    return secrets_status()


@app.put("/api/keys", dependencies=[Depends(auth)])
def put_keys(body: dict):
    save_secrets({k: (v or "") for k, v in body.items() if isinstance(v, str)})
    return secrets_status()


@app.get("/api/events", dependencies=[Depends(auth)])
def events(limit: int = 200):
    return get_db().query("events", limit=max(1, min(1000, limit)))


# ---------------------------------------------------------------- full auto mode
@app.get("/api/automation", dependencies=[Depends(auth)])
def automation_status():
    from . import automation
    return automation.status()


@app.put("/api/automation", dependencies=[Depends(auth)])
def automation_set(body: dict):
    from . import automation
    return automation.enable(bool(body.get("enabled")))


@app.post("/api/automation/run", dependencies=[Depends(auth)])
def automation_run():
    """Run one full cycle now (in the background on this server, or on the render farm)."""
    from . import automation
    if config.WORKER_MODE == "github" and _dispatch_github():
        return {"result": "Render farm started on GitHub Actions"}
    if config.ON_VERCEL:
        raise HTTPException(503, "Couldn't start the GitHub render farm: add GITHUB_TOKEN in Vercel → Settings → "
                                 "Environment Variables. The scheduled worker still runs every 6 hours.")
    run(automation.heartbeat)
    return {"result": "Automation cycle queued"}


@app.post("/api/tick", dependencies=[Depends(auth)])
def tick_now():
    if config.WORKER_MODE == "github" and _dispatch_github():
        return {"result": "Render farm started on GitHub Actions"}
    if config.ON_VERCEL:
        raise HTTPException(503, "Couldn't start the GitHub render farm: add GITHUB_TOKEN in Vercel → Settings → "
                                 "Environment Variables. The scheduled worker still runs every 6 hours.")
    run(pipeline.tick, True, 2700)
    return {"result": "Pipeline run queued"}


HEARTBEAT_EVERY = 540          # s; callers may ping more often, extra pings are no-ops
WORKER_EVERY = 5 * 3600        # s; start the render farm for queued work at most this often


def heartbeat(force: bool = False) -> dict:
    """Start whatever is due. GitHub's own cron is best-effort (runs get delayed or dropped), so an outside
    scheduler (Supabase pg_cron, Vercel Cron, any uptime pinger) pings this. Cheap and idempotent: it only
    dispatches GitHub workflows, at most once per HEARTBEAT_EVERY, so it's safe to leave public."""
    db = get_db()
    now = time.time()
    hb = db.get_setting("heartbeat", {}) or {}
    if not force and now - float(hb.get("at") or 0) < HEARTBEAT_EVERY:
        return {"ok": True, "skipped": "too soon"}
    hb["at"] = now
    out: dict = {"ok": True}
    if app_settings().get("kill_switch"):
        db.set_setting("heartbeat", hb)
        return {**out, "paused": True}
    if config.WORKER_MODE != "github":           # local/VPS: the in-process scheduler already does this
        db.set_setting("heartbeat", hb)
        return {**out, "mode": "inline"}
    ahead = (datetime.now(timezone.utc) + timedelta(hours=pipeline.PREUPLOAD_HOURS)).isoformat(timespec="seconds")
    if db.query("episodes", eq={"status": "approved"}, lte={"publish_at": ahead}, limit=1):
        out["publish"] = _dispatch_github("publish.yml")
    queued = db.query("episodes", in_={"status": ["planned", "scripted"]}, limit=1)
    if queued and now - float(hb.get("worker_at") or 0) > WORKER_EVERY:
        out["worker"] = _dispatch_github()
        if out["worker"]:
            hb["worker_at"] = now
    if out.get("publish") is False or out.get("worker") is False:
        out["github"] = _last_dispatch.get("status")      # e.g. 403 = token can't start workflows
    db.set_setting("heartbeat", hb)
    return out


@app.api_route("/api/public/heartbeat", methods=["GET", "POST"])
def public_heartbeat():
    return heartbeat()


@app.api_route("/api/cron/tick", methods=["GET", "POST"])
def cron_tick(request: Request):
    """Vercel Cron (GET, Authorization: Bearer CRON_SECRET) or any scheduler (POST, x-cron-secret header)."""
    got = request.headers.get("x-cron-secret", "")
    h = request.headers.get("authorization", "")
    if not got and h.lower().startswith("bearer "):
        got = h[7:]
    if not config.CRON_SECRET or not hmac.compare_digest(got, config.CRON_SECRET):
        raise HTTPException(401, "Bad cron secret")
    if config.WORKER_MODE == "github":
        return heartbeat(force=True)
    return {"published": pipeline.publish_due()}


# ---------------------------------------------------------------- YouTube OAuth
def _oauth_state() -> str:
    """Signed, self-contained OAuth state: works when the callback lands on another serverless instance."""
    body = f"{int(time.time())}.{secrets.token_urlsafe(12)}"
    sig = hmac.new(config.SECRET_KEY.encode(), body.encode(), "sha256").hexdigest()[:32]
    return f"{body}.{sig}"


def _state_ok(state: str, max_age: int = 900) -> bool:
    try:
        ts, nonce, sig = state.split(".")
        good = hmac.new(config.SECRET_KEY.encode(), f"{ts}.{nonce}".encode(), "sha256").hexdigest()[:32]
        return hmac.compare_digest(sig, good) and 0 <= time.time() - int(ts) <= max_age
    except (ValueError, TypeError):
        return False


def _redirect_uri(request: Request) -> str:
    base = config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return f"{base}/api/youtube/callback"


@app.get("/api/youtube/connect", dependencies=[Depends(auth)])
def yt_connect(request: Request):
    from .publish import youtube
    from .settings import secret
    if not (secret("YT_CLIENT_ID") and secret("YT_CLIENT_SECRET")):
        raise HTTPException(400, "Add YT_CLIENT_ID and YT_CLIENT_SECRET in Settings → Keys first")
    return {"url": youtube.auth_url(_redirect_uri(request), _oauth_state())}


@app.get("/api/youtube/callback")
def yt_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    from .publish import youtube
    if error or not code or not _state_ok(state):
        return RedirectResponse(f"/#/channel?yt=error&error={error or 'expired - press Connect again'}")
    try:
        youtube.exchange_code(code, _redirect_uri(request))
        get_db().set_setting("channel_cache", None)
    except Exception as e:  # noqa: BLE001
        return RedirectResponse(f"/#/channel?yt=error&error={str(e)[:80]}")
    return RedirectResponse("/#/channel?yt=ok")


# ---------------------------------------------------------------- static: media + dashboard
app.mount("/media", StaticFiles(directory=str(config.MEDIA_DIR), check_dir=False), name="media")

if (config.FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(config.FRONTEND_DIST / "assets")), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    f = config.FRONTEND_DIST / path
    if path and f.is_file() and config.FRONTEND_DIST in f.resolve().parents:
        return FileResponse(f)
    idx = config.FRONTEND_DIST / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return Response("Dashboard not built yet: cd frontend && npm install && npm run build", media_type="text/plain")
