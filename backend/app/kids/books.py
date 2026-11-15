"""Books → animated episodes.

Source: Project Gutenberg (public-domain books, free to adapt) through the Gutendex search API. A curated shelf
of children's classics from every continent is resolved by search (no hard-coded ids that could rot), any
other public-domain book can be searched, the text is downloaded, the Gutenberg header/licence is stripped,
and collections are split into separate stories. The Writer then adapts one story for the age band, with our
cast playing the roles, and the description credits the original.

Public domain note: Gutenberg texts are public domain in the USA; most of these authors died 70+ years ago, so
they are public domain almost everywhere. Newer translations can still be protected outside the US — the shelf
prefers old editions.
"""
from __future__ import annotations

import html
import re

import httpx

from .. import config

GUTENDEX = "https://gutendex.com/books"
CACHE = config.DATA_DIR / "books"

# Verified Gutenberg ids (titles checked against gutenberg.org on 2026-11-06): id, title, author, why, group.
# Any public-domain book works (search covers the whole catalogue); the Writer adapts grown-up classics gently.
SHELF = [
    # fairy tales & fables
    (19994, "The Aesop for Children", "Aesop", "Greece · 100+ short fables, each with a lesson", "Fairy tales & fables"),
    (2591, "Grimms' Fairy Tales", "Jacob & Wilhelm Grimm", "Germany · classic fairy tales (scary bits get softened)", "Fairy tales & fables"),
    (1597, "Andersen's Fairy Tales", "H. C. Andersen", "Denmark · The Ugly Duckling, The Princess and the Pea", "Fairy tales & fables"),
    (2781, "Just So Stories", "Rudyard Kipling", "India/Africa · how the elephant got his trunk", "Fairy tales & fables"),
    (14838, "The Tale of Peter Rabbit", "Beatrix Potter", "England · a naughty little rabbit", "Fairy tales & fables"),
    (62514, "Jataka Tales", "Ellen C. Babbitt", "India · the Buddha's animal fables", "Fairy tales & fables"),
    (4018, "Japanese Fairy Tales", "Yei Theodora Ozaki", "Japan · Momotaro, the Tongue-cut Sparrow", "Fairy tales & fables"),
    (18674, "A Chinese Wonder Book", "Norman Hinsdale Pitman", "China · wonder tales", "Fairy tales & fables"),
    (7128, "Indian Fairy Tales", "Joseph Jacobs", "India · folk tales", "Fairy tales & fables"),
    (66923, "West African Folk-Tales", "Barker & Sinclair", "West Africa · Anansi the spider", "Fairy tales & fables"),
    (38339, "South-African Folk-Tales", "James A. Honey", "Southern Africa · animal tales", "Fairy tales & fables"),
    (21678, "Tales of Giants from Brazil", "Elsie Spicer Eells", "Brazil · folk tales", "Fairy tales & fables"),
    (22373, "Russian Fairy Tales", "W. R. S. Ralston", "Russia · folk tales", "Fairy tales & fables"),
    (7885, "Celtic Fairy Tales", "Joseph Jacobs", "Ireland/Scotland/Wales", "Fairy tales & fables"),
    (7439, "English Fairy Tales", "Joseph Jacobs", "England · Three Little Pigs, Jack and the Beanstalk", "Fairy tales & fables"),
    (503, "The Blue Fairy Book", "Andrew Lang", "Fairy tales from many lands", "Fairy tales & fables"),
    (10607, "The Real Mother Goose", "Traditional", "Nursery rhymes · songs and chants", "Fairy tales & fables"),
    # myths & epics
    (73417, "The Great Indian Epics", "John Campbell Oman", "India · the Ramayana and the Mahabharata as stories", "Myths & epics"),
    (976, "Tanglewood Tales", "Nathaniel Hawthorne", "Greece · myths retold for young readers", "Myths & epics"),
    (1727, "The Odyssey", "Homer", "Greece · Odysseus' long journey home", "Myths & epics"),
    (128, "The Arabian Nights Entertainments", "Andrew Lang", "Middle East · Aladdin, Ali Baba (gentle versions)", "Myths & epics"),
    (18947, "The Younger Edda", "Snorri Sturluson", "Norway/Iceland · Norse myths", "Myths & epics"),
    (73766, "Maori Folk-Tales of the Port Hills", "James Cowan", "New Zealand · Maori legends", "Myths & epics"),
    (573, "Tales from Shakespeare", "Charles & Mary Lamb", "England · Shakespeare's plays as stories", "Myths & epics"),
    # classic adventures (adapted chapter by chapter)
    (11, "Alice's Adventures in Wonderland", "Lewis Carroll", "England · down the rabbit hole", "Classic adventures"),
    (500, "The Adventures of Pinocchio", "Carlo Collodi", "Italy · the puppet who wants to be real", "Classic adventures"),
    (16, "Peter Pan", "J. M. Barrie", "England · the boy who never grew up", "Classic adventures"),
    (289, "The Wind in the Willows", "Kenneth Grahame", "England · Mole, Ratty and Toad", "Classic adventures"),
    (1448, "Heidi", "Johanna Spyri", "Switzerland · a girl in the mountains", "Classic adventures"),
    (236, "The Jungle Book", "Rudyard Kipling", "India · Mowgli and his animal friends", "Classic adventures"),
    (829, "Gulliver's Travels", "Jonathan Swift", "Tiny people and giants", "Classic adventures"),
    (996, "Don Quixote", "Miguel de Cervantes", "Spain · the knight and the windmills", "Classic adventures"),
    (521, "Robinson Crusoe", "Daniel Defoe", "Shipwrecked on an island", "Classic adventures"),
    (103, "Around the World in Eighty Days", "Jules Verne", "France · a race around the world", "Classic adventures"),
    (164, "Twenty Thousand Leagues under the Sea", "Jules Verne", "A submarine under the oceans", "Classic adventures"),
    (120, "Treasure Island", "Robert Louis Stevenson", "Pirates and a treasure map (gentle)", "Classic adventures"),
    (271, "Black Beauty", "Anna Sewell", "A horse's life — kindness to animals", "Classic adventures"),
    (74, "The Adventures of Tom Sawyer", "Mark Twain", "USA · a boy's adventures on the river", "Classic adventures"),
    (1661, "The Adventures of Sherlock Holmes", "Arthur Conan Doyle", "Mysteries for big kids (puzzle episodes)", "Classic adventures"),
]



def _txt_url(gid: int) -> str:
    return f"https://www.gutenberg.org/cache/epub/{int(gid)}/pg{int(gid)}.txt"


def _gutendex_search(q: str, children: bool, limit: int) -> list[dict]:
    params = {"search": q, "languages": "en"}
    if children:
        params["topic"] = "children"
    r = httpx.get(GUTENDEX, params=params, timeout=15, follow_redirects=True)
    r.raise_for_status()
    out = []
    for b in r.json().get("results", [])[:limit]:
        if b.get("copyright"):
            continue                             # only public-domain books
        out.append({"id": b["id"], "title": b["title"], "authors": [a["name"] for a in b.get("authors", [])],
                    "subjects": b.get("subjects", [])[:5], "downloads": b.get("download_count", 0),
                    "url": f"https://www.gutenberg.org/ebooks/{b['id']}"})
    return out


def _opds_search(q: str, children: bool, limit: int) -> list[dict]:
    """Fallback: Project Gutenberg's own catalogue feed (fast, always up). Results come in relevance order."""
    query = q + (" children" if children and "child" not in q.lower() else "")
    r = httpx.get("https://www.gutenberg.org/ebooks/search.opds/", params={"query": query}, timeout=30,
                  follow_redirects=True, headers={"User-Agent": "CartoonForge/1.0"})
    r.raise_for_status()
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
        m = re.search(r"/ebooks/(\d+)\.opds", e)
        if not m:
            continue
        title = re.sub(r"\s+", " ", (re.search(r"<title>(.*?)</title>", e, re.S) or [None, ""])[1]).strip()
        author = (re.search(r"<content[^>]*>(.*?)</content>", e, re.S) or [None, ""])[1].strip()
        gid = int(m.group(1))
        out.append({"id": gid, "title": html.unescape(title), "authors": [html.unescape(author)] if author else [],
                    "subjects": [], "downloads": 1000 - len(out), "url": f"https://www.gutenberg.org/ebooks/{gid}"})
        if len(out) >= limit:
            break
    if not out and children:
        return _opds_search(q, False, limit)
    return out


def search(q: str, children: bool = False, limit: int = 25) -> list[dict]:
    """Gutenberg's own catalogue first (fast, always up); Gutendex (slow, often times out) only as a fallback.
    Copyrighted books are refused later, when the text is opened (book())."""
    try:
        hits = _opds_search(q, children, limit)
        if hits:
            return hits
    except httpx.HTTPError:
        pass
    return _gutendex_search(q, children, limit)


def shelf() -> list[dict]:
    """The curated shelf (fixed, verified ids: instant, no search luck involved)."""
    return [{"id": gid, "title": t, "authors": [au], "subjects": [], "downloads": 0, "why": why, "group": grp,
             "url": f"https://www.gutenberg.org/ebooks/{gid}"} for gid, t, au, why, grp in SHELF]


def _raw(gid: int) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{int(gid)}.raw.txt"
    if f.exists():
        return f.read_text(encoding="utf-8", errors="ignore")
    r = httpx.get(_txt_url(gid), timeout=60, follow_redirects=True, headers={"User-Agent": "CartoonForge/1.0"})
    if r.status_code == 404:
        raise ValueError("No plain-text version of this book")
    r.raise_for_status()
    raw = r.content.decode("utf-8", errors="ignore")
    f.write_text(raw, encoding="utf-8")
    return raw


def book(gid: int) -> dict:
    """Title/author from the book's own header; copyrighted Gutenberg books are refused."""
    raw = _raw(gid)
    head = raw[:4000]
    if re.search(r"copyrighted project gutenberg", head, re.I):
        raise ValueError("This book is copyrighted, not public domain")
    title = (re.search(r"^Title:\s*(.+)$", head, re.M) or [None, f"Book {gid}"])[1].strip()
    authors = [a.strip() for line in re.findall(r"^Author:\s*(.+)$", head, re.M) for a in line.split(" and ") if a.strip()]
    return {"id": int(gid), "title": title, "authors": authors, "text_url": _txt_url(gid),
            "url": f"https://www.gutenberg.org/ebooks/{int(gid)}"}


def text(gid: int) -> str:
    return strip_gutenberg(_raw(gid))


def strip_gutenberg(raw: str) -> str:
    """Keep only the book: drop the Project Gutenberg header, licence and footer."""
    t = raw.replace("\r\n", "\n")
    m = re.search(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG[^\n]*\n", t, re.I)
    if m:
        t = t[m.end():]
    m = re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG", t, re.I)
    if m:
        t = t[:m.start()]
    return t.strip()


_SKIP = re.compile(r"^(BOOK [IVXLC]+|PART [IVXLC]+|VOLUME .*|CONTENTS:?|TABLE OF CONTENTS|A LIST OF .*|LIST OF .*|PREFACE|INTRODUCTION|ILLUSTRATIONS?|LIST OF ILLUSTRATIONS|INDEX|FOOTNOTES?|NOTES?|"
                   r"THE END|FINIS|TRANSCRIBER'?S NOTE.*|APPENDIX)\.?$", re.I)


def _is_title(line: str, prev_blank: bool, next_blank: bool) -> bool:
    s = line.strip()
    if not (3 <= len(s) <= 70) or not prev_blank or not next_blank:
        return False
    letters = re.sub(r"[^A-Za-z]", "", s)
    if len(letters) < 3 or s.endswith((",", ";")):
        return False
    upper = sum(c.isupper() for c in letters) / len(letters)
    return upper > 0.85 or bool(re.match(r"^(CHAPTER|STORY|TALE|FABLE)\b", s, re.I))


def stories(body: str, min_words: int = 120, max_words: int = 6000) -> list[dict]:
    """Split a collection into stories by ALL-CAPS / CHAPTER titles. A single long story becomes one item."""
    lines = body.split("\n")
    marks = []
    for i, ln in enumerate(lines):
        pb = i == 0 or not lines[i - 1].strip()
        nb = i + 1 >= len(lines) or not lines[i + 1].strip()
        if _is_title(ln, pb, nb):
            marks.append(i)
    out = []
    for j, i in enumerate(marks):
        title = re.sub(r"\s+", " ", lines[i].strip()).strip(".")
        if _SKIP.match(title):
            continue
        end = marks[j + 1] if j + 1 < len(marks) else len(lines)
        txt = "\n".join(lines[i + 1:end]).strip()
        n = len(txt.split())
        if n < min_words:
            continue
        out.append({"index": len(out), "title": title.title() if title.isupper() else title,
                    "words": n, "text": " ".join(txt.split()[:max_words]), "preview": " ".join(txt.split()[:45]) + "…"})
    if not out:
        words = body.split()
        out = [{"index": 0, "title": "The Story", "words": len(words), "text": " ".join(words[:max_words]),
                "preview": " ".join(words[:45]) + "…"}]
    return out


def story(gid: int, index: int) -> dict:
    b = book(gid)
    items = stories(text(gid))
    if not 0 <= index < len(items):
        raise ValueError("No such story in this book")
    st = items[index]
    return {**st, "book": b["title"], "authors": b["authors"], "gutenberg_id": b["id"], "url": b["url"],
            "license": "Public domain (Project Gutenberg)"}


def credit(src: dict) -> str:
    by = ", ".join(src.get("authors") or []) or "Unknown author"
    return (f"📖 Adapted for young children from \"{src.get('title')}\" in {src.get('book')} by {by} — "
            f"public domain, via Project Gutenberg ({src.get('url')}).")
