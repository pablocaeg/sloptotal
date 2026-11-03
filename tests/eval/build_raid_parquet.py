"""Build the multi-domain RAID corpus from local parquet shards.

Same cells as build_multidomain.py (domains x {human, gpt4, chatgpt,
llama-chat, mistral-chat}, attack='none', 400-4000 chars), but reads the
dataset's parquet export instead of the Hugging Face datasets-server API, which
is often unavailable ("the dataset index is loading"). Rows are picked by a
hash of the text, so the sample is deterministic.

    # download the train shards once (~2 GB), then:
    python build_raid_parquet.py /path/to/raid/*.parquet
    -> corpus_raid.json

Requires duckdb (pip install duckdb).
"""
import json
import sys
from collections import Counter

import duckdb

DOMAINS = ["news", "books", "poetry", "abstracts"]
AI = ["gpt4", "chatgpt", "llama-chat", "mistral-chat"]
PER_CELL = 10

shards = sys.argv[1:]
if not shards:
    sys.exit(__doc__)
src = "[" + ",".join(f"'{u}'" for u in shards) + "]"
q = f"""
WITH base AS (
  SELECT domain, model, generation AS text FROM read_parquet({src})
  WHERE attack='none' AND domain IN ({",".join(f"'{d}'" for d in DOMAINS)})
    AND model IN ('human',{",".join(f"'{m}'" for m in AI)})
    AND length(generation) BETWEEN 400 AND 4000
), ranked AS (
  SELECT *, row_number() OVER (PARTITION BY domain, model ORDER BY hash(text)) rn FROM base
)
SELECT domain, model, text FROM ranked WHERE rn <= {PER_CELL}
ORDER BY domain, model, rn
"""
rows = duckdb.connect().execute(q).fetchall()
corpus = [
    {"label": "human" if m == "human" else "ai", "model": m, "domain": d, "meta": None, "text": t}
    for d, m, t in rows
]
json.dump(corpus, open("corpus_raid.json", "w", encoding="utf-8"), indent=1)
print(len(corpus), Counter((c["domain"], c["label"]) for c in corpus))
