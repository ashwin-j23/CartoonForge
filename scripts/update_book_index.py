#!/usr/bin/env python3
"""Rebuild backend/app/kids/gutenberg_index.tsv.gz from Project Gutenberg's weekly catalogue.

    python scripts/update_book_index.py                 # downloads pg_catalog.csv.gz from the PGLAF mirror
    python scripts/update_book_index.py catalog.csv.gz  # or use a file you already have

The index lets book search work instantly even when gutenberg.org is down or refuses cloud servers.
Rows: id, title, authors ("; "-joined), kids flag (1/0), up to 3 subjects. English texts only.
"""
import csv
import gzip
import io
import sys
import urllib.request
from pathlib import Path

URL = "https://gutenberg.pglaf.org/cache/epub/feeds/pg_catalog.csv.gz"
OUT = Path(__file__).resolve().parent.parent / "backend" / "app" / "kids" / "gutenberg_index.tsv.gz"


def clean(s: str) -> str:
    return " ".join((s or "").replace("\t", " ").split())


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else None
    raw = Path(src).read_bytes() if src else urllib.request.urlopen(
        urllib.request.Request(URL, headers={"User-Agent": "CartoonForge index builder"}), timeout=600).read()
    rows = []
    with gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="ignore", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("Type") != "Text" or "en" not in (r.get("Language") or "").split("; "):
                continue
            tags = f"{r.get('Subjects') or ''}; {r.get('Bookshelves') or ''}".lower()
            kids = "1" if ("juvenile" in tags or "children" in tags) else "0"
            subjects = [clean(s) for s in (r.get("Subjects") or "").split(";") if clean(s)][:3]
            rows.append("\t".join((r["Text#"], clean(r.get("Title")), clean(r.get("Authors")), kids, "; ".join(subjects))))
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as f:
        f.write("\n".join(rows) + "\n")
    print(f"{len(rows)} books -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
