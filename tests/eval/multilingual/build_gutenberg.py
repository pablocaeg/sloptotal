"""Literary control in each language: prose published before 1920, from
Project Gutenberg. As with the English classics set, a high score here is a
false positive by construction.

Books are chosen without hand-picking: the most downloaded books in the
language whose every listed person (author and translator) died by 1920,
skipping poetry and drama. Two samples per book, from the middle of the work.

Usage: python build_gutenberg.py [books_per_language] [lang ...]
"""

import csv
import io
import json
import re
import sys
import time
from pathlib import Path

import httpx

from languages import LANGUAGES, cut, is_cjk

OUT = Path(__file__).parent / "corpus"
HEADERS = {"User-Agent": "sloptotal-eval/1.0 (https://github.com/pablocaeg/sloptotal)"}
CATALOG = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
LATEST_DEATH = 1920
SAMPLES_PER_BOOK = 2
PERSON_YEARS = re.compile(r"(?:(\d{3,4})\??-(\d{3,4})\??|-(\d{3,4})\??|(\d{3,4}) BCE?-(\d{3,4}) BCE?)")
VERSE_OR_STAGE = re.compile(r"\b(poetry|poems|drama|plays|tragedies|comedies)\b", re.IGNORECASE)
START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG[^*]*\*\*\*")
END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG[^*]*\*\*\*")
RUBY = re.compile(r"《[^》]*》|｜")


def all_died_by(authors: str, year: int) -> bool:
    people = [p for p in authors.split(";") if p.strip()]
    if not people:
        return False
    for person in people:
        match = PERSON_YEARS.search(person)
        if not match:
            return False
        died = match.group(2) or match.group(3) or match.group(5)
        if not died or int(died) > year:
            return False
    return True


def eligible_books(client: httpx.Client) -> dict[int, dict]:
    raw = client.get(CATALOG, timeout=120).text
    books = {}
    for row in csv.DictReader(io.StringIO(raw)):
        if row["Type"] != "Text" or VERSE_OR_STAGE.search(row["Subjects"] + " " + row["Bookshelves"]):
            continue
        if all_died_by(row["Authors"], LATEST_DEATH):
            books[int(row["Text#"])] = row
    return books


def most_downloaded(client: httpx.Client, lang: str, pages: int = 4) -> list[int]:
    ids: list[int] = []
    for page in range(pages):
        r = client.get(
            "https://www.gutenberg.org/ebooks/search/",
            params={"query": f"l.{lang}", "sort_order": "downloads", "start_index": 1 + 25 * page},
        )
        found = [int(x) for x in re.findall(r'href="/ebooks/(\d+)"', r.text)]
        ids += [x for x in found if x not in ids]
        time.sleep(1)
    return ids


def paragraphs(raw: str, lang: str) -> list[str]:
    start, end = START.search(raw), END.search(raw)
    body = raw[start.end() : end.start()] if start and end else raw
    body = body.replace("\r\n", "\n")
    minimum = 150 if is_cjk(lang) else 60
    kept = []
    for block in body.split("\n\n"):
        if is_cjk(lang):
            text = RUBY.sub("", "".join(line.strip() for line in block.splitlines()))
        else:
            text = " ".join(block.split())
        size = len(text) if is_cjk(lang) else len(text.split())
        if size >= minimum and not re.match(r"^(CHAPTER|CAPÍTULO|CHAPITRE|KAPITEL|CAPITOLO|HOOFDSTUK)\b", text, re.I):
            kept.append(text)
    return kept


def book_text(client: httpx.Client, gid: int) -> str | None:
    for url in (
        f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt",
    ):
        r = client.get(url, timeout=90)
        if r.status_code == 200:
            return r.text
        time.sleep(2)
    return None


def build(client: httpx.Client, books: dict[int, dict], lang: str, n_books: int) -> list[dict]:
    rows: list[dict] = []
    used = 0
    for gid in most_downloaded(client, lang):
        if used >= n_books:
            break
        book = books.get(gid)
        if not book or book["Language"] != lang:
            continue
        raw = book_text(client, gid)
        if not raw:
            continue
        paras = paragraphs(raw, lang)
        middle = paras[len(paras) // 2 :]
        picked = 0
        buffer = ""
        for para in middle:
            buffer = f"{buffer} {para}".strip()
            sample = cut(buffer, lang)
            if sample is None:
                continue
            rows.append(
                {
                    "label": "human",
                    "model": "human-classic",
                    "domain": "literature",
                    "lang": lang,
                    "topic": book["Title"][:120],
                    "meta": f"https://www.gutenberg.org/ebooks/{gid} ({book['Authors'][:80]})",
                    "text": sample,
                }
            )
            picked += 1
            buffer = ""
            if picked >= SAMPLES_PER_BOOK:
                break
        if picked:
            used += 1
        time.sleep(1)
    return rows


def main() -> None:
    n_books = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    langs = sys.argv[2:] or list(LANGUAGES)
    OUT.mkdir(exist_ok=True)
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        books = eligible_books(client)
        for lang in langs:
            rows = build(client, books, lang, n_books)
            if rows:
                (OUT / f"gutenberg-{lang}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
            print(f"{lang}: {len(rows)} samples from {len({r['meta'] for r in rows})} books", flush=True)


if __name__ == "__main__":
    main()
