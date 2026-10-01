"""Modern human text in each language: Wikipedia articles as they stood on
2019-01-01, before GPT-2 was released (February 2019) and years before
ChatGPT, so no text in them can come from a modern language model.

Two kinds of machine text are excluded as well: bot-generated stubs (only
articles of 15 KB or more are drawn) and articles created with Wikipedia's
Content Translation tool, which pre-fills an article with machine translation
and tags the creating revision.

Articles are drawn at random and kept only if the pinned revision has enough
running prose after the lead section. Each sample records its revision URL,
which is also the attribution Wikipedia's CC BY-SA licence asks for.

Usage: python build_wikipedia.py [n_per_language] [lang ...]
"""

import json
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from languages import LANGUAGES, cut

PINNED = "2019-01-01T00:00:00Z"
MACHINE_TRANSLATION_TAGS = {"contenttranslation", "contenttranslation-v2"}
OUT = Path(__file__).parent / "corpus"
HEADERS = {"User-Agent": "sloptotal-eval/1.0 (https://github.com/pablocaeg/sloptotal)"}
CITATION = re.compile(r"\[\s*[\w\s]{0,12}\s*\]")
INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def api(client: httpx.Client, lang: str, **params) -> dict:
    """One API call, waiting out rate limits; Wikimedia's limit is shared across all languages."""
    for attempt in range(8):
        r = client.get(f"https://{lang}.wikipedia.org/w/api.php", params={"format": "json", **params})
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            time.sleep(int(r.headers.get("retry-after", "30")) + 5 * attempt)
        else:
            time.sleep(2 * (attempt + 1))
    r.raise_for_status()
    return {}


MIN_PAGE_BYTES = 15_000


def random_titles(client: httpx.Client, lang: str, n: int = 50) -> list[str]:
    """Random articles long enough to have several sections of prose; most random
    pages are stubs (species, villages) with a sentence or two."""
    data = api(
        client, lang, action="query", generator="random", grnnamespace=0, grnlimit=n, prop="info"
    )
    pages = data["query"]["pages"].values()
    return [page["title"] for page in pages if page.get("length", 0) >= MIN_PAGE_BYTES]


def pinned_revision(client: httpx.Client, lang: str, title: str) -> int | None:
    data = api(
        client,
        lang,
        action="query",
        prop="revisions",
        titles=title,
        rvprop="ids|timestamp",
        rvstart=PINNED,
        rvdir="older",
        rvlimit=1,
    )
    page = next(iter(data["query"]["pages"].values()))
    revisions = page.get("revisions")
    return revisions[0]["revid"] if revisions else None


def machine_translated(client: httpx.Client, lang: str, title: str) -> bool:
    data = api(
        client, lang, action="query", prop="revisions", titles=title, rvprop="tags", rvdir="newer", rvlimit=1
    )
    page = next(iter(data["query"]["pages"].values()))
    first = (page.get("revisions") or [{}])[0]
    return bool(MACHINE_TRANSLATION_TAGS & set(first.get("tags", [])))


def prose(client: httpx.Client, lang: str, revid: int) -> str:
    """Paragraph text after the lead section, without citations or tables."""
    data = api(client, lang, action="parse", oldid=revid, prop="text", disablelimitreport=1)
    soup = BeautifulSoup(data["parse"]["text"]["*"], "html.parser")
    root = soup.select_one(".mw-parser-output") or soup
    paragraphs = []
    past_lead = False
    for node in root.find_all(["p", "h2"]):
        if node.find_parent(["table", "blockquote", "figure"]):
            continue
        if node.name == "h2":
            past_lead = True
            continue
        for tag in node.select("sup, .reference, .mw-editsection, style, math"):
            tag.decompose()
        text = " ".join(INVISIBLE.sub("", CITATION.sub("", node.get_text())).split())
        if past_lead and len(text) > 80:
            paragraphs.append(text)
    return " ".join(paragraphs)


def build(lang: str, n: int) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        while len(rows) < n:
            for title in random_titles(client, lang):
                if title in seen or len(rows) >= n:
                    continue
                seen.add(title)
                revid = pinned_revision(client, lang, title)
                if not revid or machine_translated(client, lang, title):
                    continue
                sample = cut(prose(client, lang, revid), lang)
                if not sample:
                    continue
                rows.append(
                    {
                        "label": "human",
                        "model": "human-wikipedia-2018",
                        "domain": "encyclopedia",
                        "lang": lang,
                        "topic": title,
                        "meta": f"https://{lang}.wikipedia.org/w/index.php?oldid={revid}",
                        "text": sample,
                    }
                )
            time.sleep(1)
    return rows


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    langs = sys.argv[2:] or list(LANGUAGES)
    OUT.mkdir(exist_ok=True)
    for lang in langs:
        rows = build(lang, n)
        path = OUT / f"wikipedia-{lang}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"{lang}: {len(rows)} samples -> {path.name}", flush=True)


if __name__ == "__main__":
    main()
