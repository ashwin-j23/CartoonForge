"""Books keep working when gutenberg.org refuses (403) or is down: mirrors for texts, catalogue for search."""
import gzip

import httpx
import pytest

from app.kids import books

BOOK = ("The Project Gutenberg eBook of Fables\nTitle: Fables for Kids\nAuthor: Aesop\n\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK FABLES ***\n\n" + ("Once upon a time a fox met a crow. " * 60)
        + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK FABLES ***\n")
INDEX = ("19994\tThe Aesop for Children\tAesop, 620? BCE-564? BCE\t1\tFables; Children's stories\n"
         "21\tAesop's Fables\tAesop, 620? BCE-564? BCE\t0\tFables\n"
         "11\tAlice's Adventures in Wonderland\tCarroll, Lewis\t1\tFantasy fiction\n")


def test_mirror_tree_layout():
    assert books._tree(19994) == "1/9/9/9/19994"
    assert books._tree(5) == "0/5"
    urls = books._txt_urls(19994)
    assert urls[0].startswith("https://www.gutenberg.org/") and any("pglaf" in u for u in urls)


@pytest.fixture
def net(monkeypatch, tmp_path):
    monkeypatch.setattr(books, "CACHE", tmp_path)
    monkeypatch.setattr(books, "_catalog", None)
    idx = tmp_path / "index.tsv.gz"
    idx.write_bytes(gzip.compress(INDEX.encode()))
    monkeypatch.setattr(books, "INDEX", idx)
    seen = []

    def fake_get(url, **kw):
        seen.append(url)
        req = httpx.Request("GET", url)
        if "www.gutenberg.org" in url:                    # the outage: gutenberg.org refuses everyone
            return httpx.Response(403, text="Server unable to read htaccess file", request=req)
        if "gutendex" in url:
            raise httpx.ConnectTimeout("timeout", request=req)
        if url.endswith("/cache/epub/19994/pg19994.txt"):
            return httpx.Response(200, text=BOOK, request=req)
        return httpx.Response(404, request=req)

    monkeypatch.setattr(books.httpx, "get", fake_get)
    return seen


def test_text_falls_back_to_mirror(net):
    b = books.book(19994)
    assert b["title"] == "Fables for Kids" and "fox met a crow" in books.text(19994)
    assert any("pglaf" in u for u in net)
    net.clear()
    books.text(19994)                                       # cached on disk: no second download
    assert net == []


def test_missing_book_is_a_clear_error(net):
    with pytest.raises((ValueError, httpx.HTTPError)):
        books.book(12345678)


def test_search_uses_catalogue_when_gutenberg_refuses(net):
    kids = books.search("aesop", children=True)
    assert [h["id"] for h in kids] == [19994]
    every = books.search("aesop")
    assert {h["id"] for h in every} == {19994, 21}
    assert books.search("zzqx") == []


def test_bundled_index_is_real():
    books._catalog = None
    rows = books._load_catalog()
    assert len(rows) > 50000
    hits = books._catalog_search("peter rabbit", True, 10)
    assert any("Peter Rabbit" in h["title"] for h in hits)
