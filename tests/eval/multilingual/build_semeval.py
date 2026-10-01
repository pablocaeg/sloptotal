"""AI text from older generators, from SemEval-2024 Task 8 (subtask A,
multilingual; Apache-2.0): ChatGPT, LLaMA-2 and Jais in German, Italian,
Arabic and Chinese. DeepSeek alone would measure a single generator; this
adds 2023-era models from other families where the dataset has them.

Usage: python build_semeval.py [n_per_language]
"""

import json
import random
import sys
import tempfile
from pathlib import Path

import httpx
import pandas as pd

from languages import cut

OUT = Path(__file__).parent / "corpus"
BASE = "https://huggingface.co/datasets/d0rj/SemEval2024-task8/resolve/refs%2Fconvert%2Fparquet/subtaskA_multilingual"
# (split, column holding the language, its value, our code)
SOURCES = [
    ("test", "domain", "german", "de"),
    ("test", "domain", "italian", "it"),
    ("test", "domain", "arabic", "ar"),
    ("train", "source", "chinese", "zh"),
]
SEED = 20260930


def load(split: str, cache: dict) -> pd.DataFrame:
    if split not in cache:
        with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
            with httpx.stream("GET", f"{BASE}/{split}/0000.parquet", follow_redirects=True, timeout=300) as r:
                r.raise_for_status()
                for chunk in r.iter_bytes():
                    f.write(chunk)
            f.flush()
            cache[split] = pd.read_parquet(f.name)
    return cache[split]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    cache: dict = {}
    rng = random.Random(SEED)
    for split, column, value, lang in SOURCES:
        df = load(split, cache)
        ai = df[(df[column] == value) & (df["model"] != "human")]
        records = ai.to_dict("records")
        rng.shuffle(records)
        rows = []
        for record in records:
            sample = cut(record["text"], lang)
            if not sample:
                continue
            rows.append(
                {
                    "label": "ai",
                    "model": f"semeval-{record['model']}",
                    "domain": "semeval2024-task8",
                    "lang": lang,
                    "topic": "",
                    "meta": f"SemEval-2024 Task 8 subtask A multilingual, {split} id {record['id']}",
                    "text": sample,
                }
            )
            if len(rows) >= n:
                break
        (OUT / f"semeval-{lang}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        models = sorted({r["model"] for r in rows})
        print(f"{lang}: {len(rows)} samples ({', '.join(models)})", flush=True)


if __name__ == "__main__":
    main()
