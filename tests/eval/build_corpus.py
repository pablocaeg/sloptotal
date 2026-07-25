"""Assemble a labelled calibration corpus from RAID via the datasets-server API.

RAID marks human text with model == 'human'; every other model value is
machine-generated. We take attack == 'none' rows only, so we are calibrating
against clean generations rather than adversarially perturbed ones.
"""
import json
import time
import urllib.parse
import urllib.request

BASE = "https://datasets-server.huggingface.co/filter"
DATASET = "liamdugan/raid"
WANT_PER_MODEL = 12
MIN_CHARS = 500
MAX_CHARS = 4000

AI_MODELS = ["gpt4", "chatgpt", "llama-chat", "mistral-chat", "cohere-chat", "gpt3"]


def fetch(model, length=30, offset=0, tries=8):
    where = urllib.parse.quote(f"\"model\"='{model}' AND \"attack\"='none'")
    url = f"{BASE}?dataset={urllib.parse.quote(DATASET)}&config=raid&split=train&where={where}&offset={offset}&length={length}"
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                d = json.load(r)
            if "error" in d:
                time.sleep(12)
                continue
            return d.get("rows", [])
        except Exception:
            time.sleep(12)
    return []


corpus = []

# Human samples come from several domains so we are not calibrating on one genre.
human_rows = fetch("human", length=100)
picked = 0
for r in human_rows:
    g = str(r["row"].get("generation") or "").strip()
    if MIN_CHARS <= len(g) <= MAX_CHARS:
        corpus.append({"label": "human", "model": "human",
                       "domain": r["row"].get("domain"), "text": g})
        picked += 1
    if picked >= WANT_PER_MODEL * 3:
        break
print(f"human: {picked}")

for m in AI_MODELS:
    rows = fetch(m, length=60)
    n = 0
    for r in rows:
        g = str(r["row"].get("generation") or "").strip()
        if MIN_CHARS <= len(g) <= MAX_CHARS:
            corpus.append({"label": "ai", "model": m,
                           "domain": r["row"].get("domain"), "text": g})
            n += 1
        if n >= WANT_PER_MODEL:
            break
    print(f"{m}: {n}")

json.dump(corpus, open("corpus.json", "w"), indent=1)
h = sum(1 for c in corpus if c["label"] == "human")
print(f"\ntotal={len(corpus)}  human={h}  ai={len(corpus)-h}")
