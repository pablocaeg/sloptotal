"""Score every sample in corpus/ with a running SlopTotal instance.

Results are appended one line at a time and keyed by the text's hash, so an
interrupted run resumes where it stopped instead of starting over. Point it
at a local instance; the production API is for users.

Usage: SLOPTOTAL_API=http://127.0.0.1:8010/api/analyze python run_multilingual.py results.jsonl
"""

import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

CORPUS = Path(__file__).parent / "corpus"
API = os.environ.get("SLOPTOTAL_API", "http://127.0.0.1:8010/api/analyze")
WORKERS = int(os.environ.get("WORKERS", "2"))
MAX_TRIES = 5


def key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def samples() -> list[dict]:
    rows = []
    for path in sorted(CORPUS.glob("*.json")):
        for row in json.loads(path.read_text()):
            rows.append({**row, "source": path.stem, "key": key(row["text"])})
    return rows


def score(client: httpx.Client, row: dict) -> dict | None:
    for attempt in range(MAX_TRIES):
        try:
            r = client.post(API, json={"text": row["text"]})
            if r.status_code == 202:
                ticket = r.json()["ticket_id"]
                while r.status_code == 202:
                    time.sleep(2)
                    r = client.get(API.replace("/api/analyze", f"/api/queue/ticket/{ticket}"))
            r.raise_for_status()
            d = r.json()
            return {
                "key": row["key"],
                "source": row["source"],
                "lang": row["lang"],
                "label": row["label"],
                "model": row["model"],
                "domain": row["domain"],
                "meta": row["meta"],
                "overall": d["overall_score"],
                "verdict": d["overall_verdict"],
                "engines": {e["engine_name"]: e["score"] for e in d["engine_results"]},
            }
        except (httpx.HTTPError, KeyError):
            time.sleep(5 * (attempt + 1))
    return None


def main() -> None:
    out = Path(sys.argv[1])
    done = set()
    if out.exists():
        done = {json.loads(line)["key"] for line in out.read_text().splitlines() if line.strip()}
    todo = [row for row in samples() if row["key"] not in done]
    print(f"{len(done)} already scored, {len(todo)} to go", flush=True)
    started = time.time()
    with httpx.Client(timeout=600) as client, ThreadPoolExecutor(max_workers=WORKERS) as pool, out.open("a") as f:
        for i, result in enumerate(pool.map(lambda row: score(client, row), todo), 1):
            if result:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()
            if i % 25 == 0:
                rate = i / (time.time() - started)
                print(f"{i}/{len(todo)} scored, ~{(len(todo) - i) / rate / 60:.0f} min left", flush=True)
    failed = len(todo) - sum(1 for _ in out.open()) + len(done)
    print(f"done; {failed} samples failed and can be retried by running again", flush=True)


if __name__ == "__main__":
    main()
