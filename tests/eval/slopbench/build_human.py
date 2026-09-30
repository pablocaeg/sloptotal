"""SlopBench, human side: English text that provably predates ChatGPT.

Every source below was written before November 2022, most of it years before
GPT-2 (February 2019), so no sample can contain modern machine text. Each
sample keeps a `seed` — the headline, question, prompt, title or subject it
was written for — so the AI side can be generated on the same topic. Without
that pairing a detector could score well by telling subjects apart rather than
authors.

Paragraph breaks are kept: several engines read document structure, and
flattening everything to one line would make human text look unlike itself.

Sources are fetched through the Hugging Face dataset viewer API, Wikipedia's
API pinned to 2019-01-01 revisions, Project Gutenberg, and the MIT-licensed
data of Liang et al. (2023), "GPT detectors are biased against non-native
English writers". Every sample records where it came from and its licence.

Usage: python build_human.py [source ...]      (default: all)
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path

import httpx
import pyarrow.parquet as pq
from bs4 import BeautifulSoup

OUT = Path(__file__).parent / "corpus"
HEADERS = {"User-Agent": "sloptotal-eval/1.0 (https://github.com/pablocaeg/sloptotal)"}
PARQUET_API = "https://datasets-server.huggingface.co/parquet"
CACHE = Path(__file__).parent / ".cache"
SHARDS = 8
PER_SOURCE = int(os.environ.get("PER_SOURCE", "150"))
MAX_WORDS = 600
PER_PAGE = 4
LIANG = "https://raw.githubusercontent.com/Weixin-Liang/ChatGPT-Detector-Bias/main/Data_and_Results/Human_Data"

URL = re.compile(r"https?://\S+|www\.\S+")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
SENTENCE_END = re.compile(r"(?<=[.!?…\"”’])\s")
DETOKENIZE = [
    (re.compile(r" ([.,!?;:%])"), r"\1"),
    (re.compile(r" (n't|'s|'re|'ve|'ll|'d|'m)\b"), r"\1"),
    (re.compile(r"\( "), "("),
    (re.compile(r" \)"), ")"),
    (re.compile(r"`` | ''"), '"'),
]


def words(text: str) -> int:
    return len(text.split())


def tidy(text: str) -> str:
    """Normalise spacing inside paragraphs but keep the breaks between them."""
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n|\r\n\r\n", text)]
    if len(paragraphs) == 1:
        paragraphs = [" ".join(p.split()) for p in text.split("\n")]
    return "\n\n".join(p for p in paragraphs if p)


def cap(text: str, limit: int = MAX_WORDS) -> str:
    """At most `limit` words, ending on a sentence boundary."""
    if words(text) <= limit:
        return text
    kept, count = [], 0
    for paragraph in text.split("\n\n"):
        sentences = SENTENCE_END.split(paragraph)
        taken = []
        for sentence in sentences:
            if count + words(sentence) > limit:
                break
            taken.append(sentence)
            count += words(sentence)
        if taken:
            kept.append(" ".join(taken))
        if len(taken) < len(sentences):
            break
    return "\n\n".join(kept)


def detokenize(text: str) -> str:
    for pattern, replacement in DETOKENIZE:
        text = pattern.sub(replacement, text)
    return text


EXPLICIT = re.compile(
    r"\b(fuck\w*|cum|cock|dick|pussy|blowjob|porn\w*|nude|naked|rape\w*|choking|spank\w*|nigg\w*|fag\w*|retard\w*)\b",
    re.I,
)


def english_prose(text: str) -> bool:
    letters = sum(c.isalpha() for c in text)
    ascii_letters = sum(c.isascii() and c.isalpha() for c in text)
    return (
        letters > 0
        and ascii_letters / letters > 0.97
        and len(URL.findall(text)) <= 1
        and not EXPLICIT.search(text)
    )


def sample(rows: list[dict], **fields) -> dict:
    row = {"label": "human", **fields}
    row["words"] = words(row["text"])
    row["id"] = f"{row['source']}-{len(rows):04d}"
    return row


def parquet_shards(client: httpx.Client, dataset: str, config: str, split: str, rng: random.Random) -> list[Path]:
    """Download a few of the dataset's Parquet shards (cached), spread across it."""
    files = [
        f for f in client.get(PARQUET_API, params={"dataset": dataset}).json()["parquet_files"]
        if f["config"] == config and f["split"] == split
    ]
    chosen = rng.sample(files, min(len(files), SHARDS if len(files) > 50 else 1))
    chosen.sort(key=lambda f: f["filename"])
    CACHE.mkdir(exist_ok=True)
    paths = []
    for f in chosen:
        path = CACHE / f"{dataset.replace('/', '__')}-{config}-{split}-{f['filename']}"
        if not path.exists():
            with client.stream("GET", f["url"], follow_redirects=True) as r:
                r.raise_for_status()
                with open(path.with_suffix(".part"), "wb") as out:
                    for chunk in r.iter_bytes(1 << 20):
                        out.write(chunk)
            path.with_suffix(".part").rename(path)
        paths.append(path)
    return paths


def hf_rows(client: httpx.Client, dataset: str, config: str, split: str, rng: random.Random):
    """Rows in random order, in pages of 100 from random places; each page
    contributes only a few samples so no stretch of a shard (one subreddit,
    one site) dominates."""
    for path in parquet_shards(client, dataset, config, split, rng):
        table = pq.read_table(path)
        pages = list(range(0, table.num_rows, 100))
        rng.shuffle(pages)
        for start in pages:
            rows = table.slice(start, 100).to_pylist()
            rng.shuffle(rows)
            yield rows


def from_hf(name, dataset, config, split, build, min_words=150, n=PER_SOURCE):
    """Draw `n` samples; `build(row)` returns the sample fields or None to skip."""
    rng = random.Random(name)
    out: list[dict] = []
    seen_text: set[str] = set()
    with httpx.Client(headers=HEADERS, timeout=120) as client:
        for rows in hf_rows(client, dataset, config, split, rng):
            taken = 0
            for row in rows:
                fields = build(row)
                if not fields:
                    continue
                text = cap(tidy(fields.pop("text")))
                key = text[:200]
                if words(text) < min_words or not english_prose(text) or key in seen_text:
                    continue
                seen_text.add(key)
                out.append(sample(out, source=name, text=text, **fields))
                taken += 1
                if len(out) >= n or taken >= PER_PAGE:
                    break
            if len(out) >= n:
                break
    return out


def news_ccnews(row):
    if not row.get("title") or not row.get("date", "").startswith(("2016", "2017", "2018", "2019")):
        return None
    return {
        "domain": "news",
        "seed": {"headline": row["title"]},
        "date": row["date"][:10],
        "ref": row["url"],
        "license": "CC-News (Common Crawl terms of use)",
        "text": row["text"],
    }


def news_bbc(row):
    return {
        "domain": "news",
        "seed": {"summary": row["summary"]},
        "date": "2010/2017",
        "ref": f"https://www.bbc.co.uk/news/{row['id']}",
        "license": "XSum (research use)",
        "text": row["document"],
    }


def reddit(row):
    body = row["body"]
    if row["subreddit"].lower() in {"nsfw", "gonewild"} or "&gt;" in body or body.count("*") > 6:
        return None
    return {
        "domain": "social",
        "seed": {"subreddit": row["subreddit"], "point": row["summary"]},
        "date": "2006/2016",
        "ref": f"https://www.reddit.com/comments/{row['id']}",
        "license": "Webis-TLDR-17 (research use)",
        "text": MARKDOWN_LINK.sub(r"\1", body),
    }


def eli5(row):
    return {
        "domain": "explanation",
        "seed": {"question": row["question"]},
        "date": "2012/2019",
        "ref": "https://www.reddit.com/r/explainlikeimfive/",
        "license": "ELI5 (research use)",
        "text": MARKDOWN_LINK.sub(r"\1", row["answer"]),
    }


SE_API = "https://api.stackexchange.com/2.3"
SE_SITES = [
    "cooking", "travel", "parenting", "workplace", "academia", "law", "history", "philosophy", "writing",
    "diy", "money", "outdoors", "pets", "fitness", "gardening", "interpersonal", "english", "movies",
    "literature", "music", "bicycles", "astronomy", "biology", "skeptics", "politics",
]
SE_CUTOFF = 1640995200


def se_get(client: httpx.Client, path: str, **params) -> list[dict]:
    for attempt in range(5):
        r = client.get(f"{SE_API}{path}", params={"filter": "withbody", **params})
        if r.status_code == 200:
            data = r.json()
            time.sleep(data.get("backoff", 0) + 0.5)
            return data["items"]
        time.sleep(10 * (attempt + 1))
    r.raise_for_status()
    return []


def se_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.find_all(["p", "li", "blockquote"]) or [soup]
    return "\n\n".join(" ".join(b.get_text(" ").split()) for b in blocks if not b.find_parent(["li", "blockquote"]))


def stackexchange(n: int = PER_SOURCE) -> list[dict]:
    """Top-voted answers on non-technical sites, written and last edited before
    2022, so no later AI rewrite can have slipped in."""
    rng = random.Random("qa-stackexchange")
    per_site = -(-n // len(SE_SITES))
    out: list[dict] = []
    with httpx.Client(headers=HEADERS, timeout=60) as client:
        for site in SE_SITES:
            by_id: dict[int, dict] = {}
            for year in rng.sample(range(2014, 2022), 3):
                questions = se_get(
                    client, "/questions", site=site, sort="votes", order="desc", pagesize=40,
                    fromdate=int(time.mktime((year, 1, 1, 0, 0, 0, 0, 0, 0))),
                    todate=int(time.mktime((year + 1, 1, 1, 0, 0, 0, 0, 0, 0))),
                )
                by_id = {q["question_id"]: q for q in questions}
                if by_id:
                    break
            if not by_id:
                continue
            answers = se_get(
                client, f"/questions/{';'.join(map(str, by_id))}/answers",
                site=site, sort="votes", order="desc", pagesize=100,
            )
            taken: set[int] = set()
            for answer in answers:
                qid = answer["question_id"]
                edited = answer.get("last_edit_date", answer["creation_date"])
                if qid in taken or max(answer["creation_date"], edited) >= SE_CUTOFF or "<pre" in answer["body"]:
                    continue
                text = cap(se_text(answer["body"]))
                if words(text) < 120 or not english_prose(text):
                    continue
                taken.add(qid)
                question = by_id[qid]
                out.append(
                    sample(
                        out,
                        source="qa-stackexchange",
                        domain="qa",
                        seed={
                            "question": BeautifulSoup(question["title"], "html.parser").get_text(),
                            "site": f"{site}.stackexchange.com",
                        },
                        date=time.strftime("%Y-%m-%d", time.gmtime(answer["creation_date"])),
                        ref=f"https://{site}.stackexchange.com/a/{answer['answer_id']}",
                        license=f"CC BY-SA 4.0 (Stack Exchange; answer by {answer['owner'].get('display_name', 'unknown')})",
                        text=text,
                    )
                )
                if len(taken) >= per_site or len(out) >= n:
                    break
            print(f"  {site}: {len(taken)}", flush=True)
    return out[:n]


ARXIV_FIELDS = {
    "cs": "computer science", "math": "mathematics", "stat": "statistics", "econ": "economics",
    "eess": "electrical engineering", "q-bio": "quantitative biology", "q-fin": "quantitative finance",
    "astro-ph": "astrophysics", "cond-mat": "condensed matter physics", "quant-ph": "quantum physics",
}


def arxiv_field(categories: list[str]) -> str:
    first = categories[0].split()[0]
    prefix = first.split(".")[0]
    return ARXIV_FIELDS.get(prefix, "physics")


def arxiv(row):
    year = 2000 + int(row["id"][:2]) if row["id"][:2].isdigit() and row["id"][4] == "." else None
    if not year or year < 2010:
        return None
    return {
        "domain": "academic",
        "seed": {"title": " ".join(row["title"].split()), "field": arxiv_field(row["categories"])},
        "date": str(year),
        "ref": f"https://arxiv.org/abs/{row['id']}",
        "license": "arXiv metadata (CC0)",
        "text": " ".join(row["abstract"].split()),
    }


def writingprompts(row):
    prompt = detokenize(re.sub(r"^\[\s*\w+\s*\]\s*", "", row["prompt"])).strip()
    story = detokenize(row["story"].replace("<newline>", "\n"))
    return {
        "domain": "creative",
        "seed": {"prompt": prompt},
        "date": "2017/2018",
        "ref": "https://www.reddit.com/r/WritingPrompts/",
        "license": "WritingPrompts (research use)",
        "text": story,
    }


def reviews(row):
    return {
        "domain": "review",
        "seed": {"title": row["title"], "sentiment": "positive" if row["label"] == 1 or row["label"] == "1" else "negative"},
        "date": "1995/2013",
        "ref": "https://huggingface.co/datasets/fancyzhx/amazon_polarity",
        "license": "Amazon reviews (research use)",
        "text": row["content"],
    }


SOURCES_HF = {
    "news-ccnews": ("vblagoje/cc_news", "plain_text", "train", news_ccnews, 150, PER_SOURCE * 3 // 5),
    "news-bbc": ("EdinburghNLP/xsum", "default", "train", news_bbc, 150, PER_SOURCE * 2 // 5),
    "social-reddit": ("webis/tldr-17", "default", "train", reddit, 120, PER_SOURCE),
    "explanation-eli5": ("sentence-transformers/eli5", "pair", "train", eli5, 120, PER_SOURCE),
    "academic-arxiv": ("gfissore/arxiv-abstracts-2021", "default", "train", arxiv, 120, PER_SOURCE),
    "creative-writingprompts": ("euclaise/writingprompts", "default", "train", writingprompts, 200, PER_SOURCE),
    "review-amazon": ("fancyzhx/amazon_polarity", "amazon_polarity", "train", reviews, 70, PER_SOURCE),
}


def liang(name: str, folder: str, domain: str, note: str, label: str = "human") -> list[dict]:
    data = httpx.get(f"{LIANG}/{folder}/data.json", headers=HEADERS, timeout=60).json()
    out: list[dict] = []
    for item in data:
        text = tidy(item["document"])
        out.append(
            sample(
                out,
                source=name,
                label=label,
                domain=domain,
                seed={},
                date="before 2022",
                ref=f"https://github.com/Weixin-Liang/ChatGPT-Detector-Bias/tree/main/Data_and_Results/Human_Data/{folder}",
                license="MIT (Liang et al. 2023)",
                note=note,
                text=text,
            )
        )
    return out


PINNED = "2019-01-01T00:00:00Z"
CITATION = re.compile(r"\[\s*[\w\s]{0,12}\s*\]")


def wiki_api(client: httpx.Client, site: str = "en.wikipedia.org", **params) -> dict:
    for attempt in range(8):
        r = client.get(f"https://{site}/w/api.php", params={"format": "json", **params})
        if r.status_code == 200:
            return r.json()
        time.sleep(int(r.headers.get("retry-after", "10")) + 5 * attempt)
    r.raise_for_status()
    return {}


def wiki_prose(client: httpx.Client, revid: int, site: str = "en.wikipedia.org", skip_lead: bool = True) -> str:
    """Paragraphs after the lead section, without citations or tables."""
    data = wiki_api(client, site, action="parse", oldid=revid, prop="text", disablelimitreport=1)
    if "parse" not in data:
        return ""
    soup = BeautifulSoup(data["parse"]["text"]["*"], "html.parser")
    root = soup.select_one(".mw-parser-output") or soup
    paragraphs, past_lead = [], False
    for node in root.find_all(["p", "h2"]):
        if node.find_parent(["table", "blockquote", "figure"]):
            continue
        if node.name == "h2":
            past_lead = True
            continue
        for tag in node.select("sup, .reference, .mw-editsection, style, math"):
            tag.decompose()
        text = " ".join(CITATION.sub("", node.get_text()).split())
        if (past_lead or not skip_lead) and len(text) > 80:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def wikipedia(n: int = PER_SOURCE) -> list[dict]:
    """Random articles of 15 KB or more (most random pages are stubs), as they
    stood on 2019-01-01."""
    out: list[dict] = []
    seen: set[str] = set()
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        while len(out) < n:
            data = wiki_api(client, action="query", generator="random", grnnamespace=0, grnlimit=50, prop="info")
            for page in data["query"]["pages"].values():
                title = page["title"]
                if page.get("length", 0) < 15_000 or title in seen or len(out) >= n:
                    continue
                seen.add(title)
                revs = wiki_api(
                    client, action="query", prop="revisions", titles=title,
                    rvprop="ids|timestamp", rvstart=PINNED, rvdir="older", rvlimit=1,
                )
                revisions = next(iter(revs["query"]["pages"].values())).get("revisions")
                if not revisions:
                    continue
                text = cap(wiki_prose(client, revisions[0]["revid"]), 400)
                if words(text) < 150:
                    continue
                out.append(
                    sample(
                        out,
                        source="encyclopedia-wikipedia",
                        domain="encyclopedia",
                        seed={"title": title},
                        date=revisions[0]["timestamp"][:10],
                        ref=f"https://en.wikipedia.org/w/index.php?oldid={revisions[0]['revid']}",
                        license="CC BY-SA 3.0 (Wikipedia)",
                        text=text,
                    )
                )
            time.sleep(1)
    return out


WIKINEWS = "en.wikinews.org"
DATELINE = re.compile(r"^\w+day, \w+ \d{1,2}, \d{4}\s*")
WIKINEWS_PINNED = "2022-10-31T00:00:00Z"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def wikinews(n: int = 90) -> list[dict]:
    """News written after GPT-2's training data was collected (2019) and before
    ChatGPT: Wikinews articles published March 2020 – October 2022, as they
    stood on 2022-10-31. Separates "old news a model memorised" from "news"."""
    rng = random.Random("news-wikinews")
    out: list[dict] = []
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        titles: list[tuple[str, str]] = []
        for year in (2020, 2021, 2022):
            for month in MONTHS[2 if year == 2020 else 0 : 10 if year == 2022 else 12]:
                days = wiki_api(
                    client, WIKINEWS, action="query", list="categorymembers",
                    cmtitle=f"Category:{month} {year}", cmtype="subcat", cmlimit=50,
                )["query"]["categorymembers"]
                for day in days:
                    pages = wiki_api(
                        client, WIKINEWS, action="query", list="categorymembers",
                        cmtitle=day["title"], cmtype="page", cmnamespace=0, cmlimit=50,
                    )["query"]["categorymembers"]
                    titles += [(p["title"], day["title"].removeprefix("Category:")) for p in pages]
        rng.shuffle(titles)
        seen: set[str] = set()
        for title, day in titles:
            if title in seen or len(out) >= n:
                continue
            seen.add(title)
            revs = wiki_api(
                client, WIKINEWS, action="query", prop="revisions", titles=title,
                rvprop="ids|timestamp", rvstart=WIKINEWS_PINNED, rvdir="older", rvlimit=1,
            )
            revisions = next(iter(revs["query"]["pages"].values())).get("revisions")
            if not revisions:
                continue
            text = cap(DATELINE.sub("", wiki_prose(client, revisions[0]["revid"], WIKINEWS, skip_lead=False)))
            if words(text) < 150 or not english_prose(text):
                continue
            out.append(
                sample(
                    out,
                    source="news-wikinews",
                    domain="news",
                    seed={"headline": title},
                    date=day,
                    ref=f"https://{WIKINEWS}/w/index.php?oldid={revisions[0]['revid']}",
                    license="CC BY 2.5 (Wikinews)",
                    text=text,
                )
            )
    return out


BOOKS = [
    (1342, "Pride and Prejudice", "Jane Austen", 1813),
    (2701, "Moby-Dick", "Herman Melville", 1851),
    (1661, "The Adventures of Sherlock Holmes", "Arthur Conan Doyle", 1892),
    (98, "A Tale of Two Cities", "Charles Dickens", 1859),
    (174, "The Picture of Dorian Gray", "Oscar Wilde", 1890),
    (1232, "The Prince", "Niccolò Machiavelli (trans.)", 1532),
    (5200, "Metamorphosis", "Franz Kafka (trans.)", 1915),
    (84, "Frankenstein", "Mary Shelley", 1818),
    (2814, "Dubliners", "James Joyce", 1914),
    (11, "Alice's Adventures in Wonderland", "Lewis Carroll", 1865),
    (1260, "Jane Eyre", "Charlotte Brontë", 1847),
    (768, "Wuthering Heights", "Emily Brontë", 1847),
    (345, "Dracula", "Bram Stoker", 1897),
    (76, "Adventures of Huckleberry Finn", "Mark Twain", 1884),
    (205, "Walden", "Henry David Thoreau", 1854),
    (1400, "Great Expectations", "Charles Dickens", 1861),
    (145, "Middlemarch", "George Eliot", 1871),
    (2600, "War and Peace", "Leo Tolstoy (trans.)", 1869),
    (28054, "The Brothers Karamazov", "Fyodor Dostoevsky (trans.)", 1880),
    (160, "The Awakening", "Kate Chopin", 1899),
    (43, "The Strange Case of Dr Jekyll and Mr Hyde", "R. L. Stevenson", 1886),
    (219, "Heart of Darkness", "Joseph Conrad", 1899),
    (4300, "Ulysses", "James Joyce", 1922),
    (3207, "Leviathan", "Thomas Hobbes", 1651),
    (3300, "The Wealth of Nations", "Adam Smith", 1776),
    (1497, "The Republic", "Plato (trans. Jowett)", 1871),
    (7370, "Second Treatise of Government", "John Locke", 1690),
    (34901, "On Liberty", "John Stuart Mill", 1859),
    (1228, "On the Origin of Species", "Charles Darwin", 1859),
    (2680, "Meditations", "Marcus Aurelius (trans.)", 1862),
]
CLASSIC_CHUNKS = 3


def gutenberg_paragraphs(gid: int) -> list[str]:
    for url in (f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt", f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt"):
        r = httpx.get(url, headers=HEADERS, timeout=90, follow_redirects=True)
        if r.status_code == 200:
            raw = r.text.replace("\r\n", "\n")
            start = re.search(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG[^*]*\*\*\*", raw)
            end = re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG[^*]*\*\*\*", raw)
            body = raw[start.end() : end.start()] if start and end else raw
            return [
                " ".join(p.split())
                for p in body.split("\n\n")
                if words(p) >= 40 and not re.match(r"^\s*(CHAPTER|BOOK|ACT|SCENE|PART)\b", p, re.I)
            ]
        time.sleep(3)
    return []


def classics() -> list[dict]:
    """Passages from the middle of each work: a high score on any of them is a
    false positive by construction."""
    out: list[dict] = []
    for gid, title, author, year in BOOKS:
        paragraphs = gutenberg_paragraphs(gid)
        middle = paragraphs[len(paragraphs) // 3 : 2 * len(paragraphs) // 3]
        step = max(1, len(middle) // CLASSIC_CHUNKS)
        for start in range(0, len(middle), step)[:CLASSIC_CHUNKS]:
            chunk, count = [], 0
            for paragraph in middle[start:]:
                chunk.append(paragraph)
                count += words(paragraph)
                if count >= 250:
                    break
            text = cap("\n\n".join(chunk), 350)
            if words(text) >= 150:
                out.append(
                    sample(
                        out,
                        source="classics-gutenberg",
                        domain="literature",
                        seed={"title": title, "author": author},
                        date=str(year),
                        ref=f"https://www.gutenberg.org/ebooks/{gid}",
                        license="Public domain (Project Gutenberg)",
                        text=text,
                    )
                )
        print(f"  {title}: {sum(1 for r in out if r['seed']['title'] == title)}", flush=True)
    return out


def build(name: str) -> list[dict]:
    if name in SOURCES_HF:
        dataset, config, split, fn, min_words, n = SOURCES_HF[name]
        return from_hf(name, dataset, config, split, fn, min_words, n)
    if name == "news-wikinews":
        return wikinews()
    if name == "qa-stackexchange":
        return stackexchange()
    if name == "encyclopedia-wikipedia":
        return wikipedia()
    if name == "classics-gutenberg":
        return classics()
    if name == "essay-toefl":
        return liang(name, "TOEFL_real_91", "essay", "TOEFL essays by non-native English writers")
    if name == "essay-hewlett":
        return liang(name, "HewlettStudentEssay_real_88", "essay", "US 8th-grade student essays (Hewlett ASAP)")
    if name == "essay-college":
        return liang(name, "CollegeEssay_real_70", "essay", "US college admission essays")
    if name == "mixed-toefl-polished":
        return liang(
            name, "TOEFL_gpt4polished_91", "essay",
            "The TOEFL essays with word choice polished by GPT-4", label="human-ai-polished",
        )
    raise SystemExit(f"unknown source {name}")


ALL = [*SOURCES_HF, "news-wikinews", "qa-stackexchange", "encyclopedia-wikipedia", "classics-gutenberg", "essay-toefl", "essay-hewlett", "essay-college", "mixed-toefl-polished"]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name in sys.argv[1:] or ALL:
        rows = build(name)
        path = OUT / f"human-{name}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        mean = sum(r["words"] for r in rows) / max(1, len(rows))
        print(f"{name}: {len(rows)} samples, mean {mean:.0f} words -> {path.name}", flush=True)


if __name__ == "__main__":
    main()
