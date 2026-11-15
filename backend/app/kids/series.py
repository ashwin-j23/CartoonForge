"""Automatic book series: the studio works through a book story by story, one episode per story.

Switch on with the `book_series` setting. The planner (pipeline._keep_full) keeps `book_series_per_day` × 2 book
episodes in the queue; each one is the NEXT story of the current book (story 1, 2, 3 … 109). When a book is
finished the next book of the curated children's shelf starts by itself (or the one you choose).

State (setting "book_series"): {gid, title, authors, total, titles, next, done: [gid, …], started_at}.
"""
from __future__ import annotations

import threading

from ..db import get_db, now_iso
from ..settings import app_settings
from . import books

KEY = "book_series"
_lock = threading.Lock()


def _state() -> dict:
    return dict(get_db().get_setting(KEY, {}) or {})


def _save(st: dict) -> dict:
    get_db().set_setting(KEY, st)
    return st


def choose(gid: int, start: int = 0) -> dict:
    """Make this book the current series book (downloads it once to count its stories)."""
    b = books.book(int(gid))
    items = books.stories(books.text(int(gid)))
    if not items:
        raise ValueError("No stories found in this book")
    st = _state()
    done = [g for g in st.get("done", []) if g != b["id"]]
    return _save({"gid": b["id"], "title": b["title"], "authors": b["authors"], "total": len(items),
                  "titles": [i["title"] for i in items], "next": max(0, min(int(start), len(items) - 1)),
                  "done": done, "started_at": now_iso()})


def _next_shelf_book(done: list[int], current: int | None) -> int | None:
    for b in books.shelf():
        if b["id"] not in done and b["id"] != current:
            return b["id"]
    return None


def _ensure_book(st: dict) -> dict:
    """A current book with stories left, moving on to the next shelf book when one is finished."""
    if st.get("gid") and st.get("next", 0) < st.get("total", 0):
        return st
    done = list(st.get("done", []))
    if st.get("gid") and st["gid"] not in done:
        done.append(st["gid"])
    for _ in range(len(books.shelf()) + 1):
        gid = _next_shelf_book(done, None)
        if gid is None:                                  # every shelf book done: start the shelf again
            done, gid = [], books.shelf()[0]["id"]
        _save({**st, "done": done})
        try:
            return choose(gid)
        except (ValueError, OSError) as e:               # a book without usable stories: skip it
            get_db().log(f"Book series: skipped book {gid} ({e})", "warn")
            done.append(gid)
    raise ValueError("No usable book for the series")


def take_next() -> dict:
    """Reserve the next story (advances the pointer first, so two planners never take the same story)."""
    with _lock:
        st = _ensure_book(_state())
        idx = int(st["next"])
        _save({**st, "next": idx + 1})
    src = books.story(int(st["gid"]), idx)
    src["series"] = {"gid": st["gid"], "index": idx, "total": st["total"]}
    return src


def plan_one():
    """Create the next book-series episode (called by the planner)."""
    from ..pipeline import create
    src = take_next()
    n, total = src["series"]["index"] + 1, src["series"]["total"]
    return create(source=src, why=f"Book series: {src['book']} — story {n} of {total}")


def pending_count(rows: list[dict]) -> int:
    return sum(1 for e in rows if (e.get("source") or {}).get("series"))


def skip(n: int = 1) -> dict:
    with _lock:
        st = _state()
        if not st.get("gid"):
            raise ValueError("No series book yet")
        st["next"] = max(0, min(int(st.get("next", 0)) + int(n), int(st.get("total", 0))))
        return _save(st)


def restart() -> dict:
    with _lock:
        st = _state()
        if not st.get("gid"):
            raise ValueError("No series book yet")
        return _save({**st, "next": 0})


def status() -> dict:
    s, st = app_settings(), _state()
    nxt, titles = int(st.get("next", 0)), st.get("titles") or []
    shelf = {b["id"]: b["title"] for b in books.shelf()}
    rows = get_db().query("episodes", in_={"status": ["planned", "writing", "scripted", "rendering", "review",
                                                      "approved", "published"]}, limit=300)
    made = [{"id": e["id"], "status": e["status"], "index": e["source"]["series"]["index"],
             "title": (e.get("meta") or {}).get("title") or e.get("topic")}
            for e in rows if st.get("gid") and ((e.get("source") or {}).get("series") or {}).get("gid") == st["gid"]]
    return {"enabled": bool(s.get("book_series")), "per_day": int(s.get("book_series_per_day", 1)),
            "book": {k: st.get(k) for k in ("gid", "title", "authors", "total", "started_at")} if st.get("gid") else None,
            "next": nxt, "upcoming": [{"index": i, "title": titles[i]} for i in range(nxt, min(nxt + 5, len(titles)))],
            "made": sorted(made, key=lambda m: m["index"]),
            "done": [{"gid": g, "title": shelf.get(g, f"Book {g}")} for g in st.get("done", [])],
            "next_book": shelf.get(_next_shelf_book(st.get("done", []), st.get("gid")))}
