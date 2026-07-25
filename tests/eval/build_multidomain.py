"""Stratified multi-domain corpus from RAID.

The earlier corpus accidentally sampled a single domain (abstracts), so its
headline AUC said nothing about how the ensemble behaves on news, prose or
poetry. This samples each domain explicitly and keeps the domain label so
per-domain AUC can be computed.
"""
import json
import time
import urllib.parse
import urllib.request

BASE = "https://datasets-server.huggingface.co/filter"
DOMAINS = ["news", "books", "poetry", "abstracts"]
AI_MODELS = ["gpt4", "chatgpt", "llama-chat", "mistral-chat"]
PER_CELL = 10
MIN_CHARS, MAX_CHARS = 400, 4000


def fetch(where, length=60, tries=6):
    url = (
        f"{BASE}?dataset={urllib.parse.quote('liamdugan/raid')}&config=raid&split=train"
        f"&where={urllib.parse.quote(where)}&length={length}"
    )
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                d = json.load(r)
            if "error" in d:
                time.sleep(10)
                continue
            return d.get("rows", [])
        except Exception:
            time.sleep(10)
    return []


corpus = []
for dom in DOMAINS:
    rows = fetch(f"\"domain\"='{dom}' AND \"model\"='human' AND \"attack\"='none'", 80)
    n = 0
    for r in rows:
        g = str(r["row"].get("generation") or "").strip()
        if MIN_CHARS <= len(g) <= MAX_CHARS:
            corpus.append({"label": "human", "model": "human", "domain": dom, "text": g})
            n += 1
        if n >= PER_CELL:
            break
    print(f"{dom:10} human={n}", flush=True)

    for m in AI_MODELS:
        rows = fetch(f"\"domain\"='{dom}' AND \"model\"='{m}' AND \"attack\"='none'", 40)
        k = 0
        for r in rows:
            g = str(r["row"].get("generation") or "").strip()
            if MIN_CHARS <= len(g) <= MAX_CHARS:
                corpus.append({"label": "ai", "model": m, "domain": dom, "text": g})
                k += 1
            if k >= PER_CELL // 2:
                break
        print(f"{dom:10} {m:14} ai={k}", flush=True)

json.dump(corpus, open("corpus_multidomain.json", "w"), indent=1)
h = sum(1 for c in corpus if c["label"] == "human")
print(f"\ntotal={len(corpus)} human={h} ai={len(corpus)-h}")
