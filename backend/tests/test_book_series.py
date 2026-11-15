"""Automatic book series: next story each time, books roll over, planner keeps the share, API works."""
import pytest

from app import pipeline
from app.db import get_db
from app.kids import books, series
from app.settings import save_app_settings

FAKE = {101: ["The Fox", "The Crow", "The Lion"], 202: ["Only Story"]}


@pytest.fixture
def fake_books(monkeypatch):
    shelf = [{"id": g, "title": f"Book {g}"} for g in FAKE]
    monkeypatch.setattr(books, "shelf", lambda: shelf)
    monkeypatch.setattr(books, "book", lambda gid: {"id": gid, "title": f"Book {gid}", "authors": ["A. Author"],
                                                    "url": f"https://www.gutenberg.org/ebooks/{gid}"})
    monkeypatch.setattr(books, "text", lambda gid: str(gid))
    monkeypatch.setattr(books, "stories", lambda body: [{"index": i, "title": t, "words": 300, "text": t * 50,
                                                         "preview": t} for i, t in enumerate(FAKE[int(body)])])
    get_db().set_setting(series.KEY, {})
    yield


def test_takes_stories_in_order_and_rolls_to_next_book(fake_books):
    got = [series.take_next() for _ in range(5)]
    assert [(s["gutenberg_id"], s["series"]["index"], s["title"]) for s in got] == [
        (101, 0, "The Fox"), (101, 1, "The Crow"), (101, 2, "The Lion"), (202, 0, "Only Story"), (101, 0, "The Fox")]
    assert got[0]["book"] == "Book 101" and got[0]["series"]["total"] == 3


def test_choose_skip_restart(fake_books):
    series.choose(202)
    assert series.take_next()["gutenberg_id"] == 202
    series.choose(101, start=1)
    series.skip()
    assert series.take_next()["title"] == "The Lion"
    series.restart()
    assert series.take_next()["title"] == "The Fox"


def test_planner_keeps_book_share(fake_books, monkeypatch):
    db = get_db()
    for e in db.query("episodes", limit=500):
        db.delete("episodes", e["id"])
    monkeypatch.setattr(pipeline, "has_ai", lambda: True)
    save_app_settings({"auto_generate": True, "episodes_per_day": 3, "book_series": True, "book_series_per_day": 1})
    pipeline._keep_full()
    pipeline._keep_full()
    eps = [e for e in db.query("episodes", limit=50) if e["status"] == "planned"]
    book_eps = [e for e in eps if (e.get("source") or {}).get("series")]
    assert len(book_eps) == 2                                  # 1 a day x 2 days in the queue
    assert sorted(e["source"]["series"]["index"] for e in book_eps) == [0, 1]
    assert all(e["category"] == "books" and "story" in e["why"] for e in book_eps)
    assert len(eps) > len(book_eps)                            # normal topic episodes still planned
    save_app_settings({"book_series": False})


def test_api(fake_books):
    from fastapi.testclient import TestClient
    from app import config, main
    c = TestClient(main.app)
    h = {"Authorization": "Bearer " + c.post("/api/login", json={"password": config.ADMIN_PASSWORD}).json()["token"]}
    st = c.put("/api/books/series", headers=h, json={"enabled": True, "per_day": 2}).json()
    assert st["enabled"] and st["per_day"] == 2 and st["book"]["gid"] == 101 and st["upcoming"][0]["title"] == "The Fox"
    st = c.post("/api/books/series/skip", headers=h, json={}).json()
    assert st["next"] == 1
    st = c.put("/api/books/series", headers=h, json={"gid": 202}).json()
    assert st["book"]["title"] == "Book 202" and st["next_book"] == "Book 101"
    c.put("/api/books/series", headers=h, json={"enabled": False})
