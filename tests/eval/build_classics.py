"""Second validation set: pre-1920 public-domain prose from Project Gutenberg.

RAID tells us how the ensemble behaves on modern web text. It cannot tell us
anything about the failure mode we actually observed -- canonical literature
being scored as AI because GPT-2 has effectively memorised it, making it look
maximally predictable.

Every text here was published decades before any language model existed, so a
high score is a false positive by construction. Weights and thresholds must be
chosen against BOTH sets: optimising on RAID alone would lower the threshold and
turn these into confident misclassifications.
"""
import json
import re
import time
import urllib.request

# (Gutenberg id, title, author, year)
BOOKS = [
    (1342, "Pride and Prejudice", "Austen", 1813),
    (2701, "Moby-Dick", "Melville", 1851),
    (1661, "Adventures of Sherlock Holmes", "Doyle", 1892),
    (98, "A Tale of Two Cities", "Dickens", 1859),
    (174, "The Picture of Dorian Gray", "Wilde", 1890),
    (1080, "A Modest Proposal", "Swift", 1729),
    (2542, "A Doll's House", "Ibsen", 1879),
    (16328, "Beowulf", "trans. Gummere", 1910),
    (2814, "Dubliners", "Joyce", 1914),
    (1232, "The Prince", "Machiavelli", 1532),
    (5200, "Metamorphosis", "Kafka", 1915),
    (84, "Frankenstein", "Shelley", 1818),
]

CHUNKS_PER_BOOK = 3
CHUNK_WORDS = 220


def fetch_text(gid):
    for url in (
        f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt",
    ):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sloptotal-eval/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            time.sleep(3)
    return None


def clean_body(raw):
    """Strip Gutenberg licence headers/footers and normalise whitespace."""
    start = re.search(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG[^\*]*\*\*\*", raw)
    end = re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG[^\*]*\*\*\*", raw)
    body = raw[start.end() : end.start()] if start and end else raw
    # Drop transcriber notes and chapter headings; keep flowing prose.
    body = re.sub(r"\r\n", "\n", body)
    paras = [p.strip() for p in body.split("\n\n")]
    paras = [
        re.sub(r"\s+", " ", p)
        for p in paras
        if len(p.split()) >= 60 and not re.match(r"^(CHAPTER|BOOK|ACT|SCENE|PART)\b", p.strip(), re.I)
    ]
    return paras


corpus = []
for gid, title, author, year in BOOKS:
    raw = fetch_text(gid)
    if not raw:
        print(f"  {title}: FETCH FAILED")
        continue
    paras = clean_body(raw)
    # Sample from the middle of the work, away from front/back matter.
    mid = len(paras) // 2
    picked = 0
    for p in paras[mid : mid + 40]:
        words = p.split()
        if len(words) < CHUNK_WORDS:
            continue
        corpus.append({
            "label": "human",
            "model": "human-classic",
            "domain": "literature",
            "meta": f"{author} {year} — {title}",
            "text": " ".join(words[:CHUNK_WORDS]),
        })
        picked += 1
        if picked >= CHUNKS_PER_BOOK:
            break
    print(f"  {title[:34]:34} {author:16} {year}  chunks={picked}", flush=True)

json.dump(corpus, open("corpus_classics.json", "w"), indent=1)
print(f"\ntotal classic human chunks: {len(corpus)}")
