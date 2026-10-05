"""Score every SlopBench sample with a running SlopTotal instance.

Results are appended one line at a time, keyed by sample id and text hash, so
an interrupted run resumes where it stopped. A queued request (HTTP 202) is
polled until its ticket completes. Point it at a local instance; the
production API is for users.

Usage: SLOPTOTAL_URL=http://127.0.0.1:8010 python score.py results.jsonl
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
BASE = os.environ.get("SLOPTOTAL_URL", "http://127.0.0.1:8010").rstrip("/")
WORKERS = int(os.environ.get("WORKERS", "2"))
MAX_TRIES = 5
KEPT = ("id", "label", "source", "domain", "model", "variant", "base", "base_model", "words")


def key(row: dict) -> str:
    return f"{row['id']}:{hashlib.sha256(row['text'].encode()).hexdigest()[:12]}"


def samples() -> list[dict]:
    rows = []
    for path in sorted(CORPUS.glob("*.jsonl")):
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows


def analyse(client: httpx.Client, text: str) -> dict:
    r = client.post(f"{BASE}/api/analyze", json={"text": text})
    while r.status_code == 429:
        time.sleep(float(r.json().get("retry_after", 2)))
        r = client.post(f"{BASE}/api/analyze", json={"text": text})
    if r.status_code == 202:
        ticket = r.json()["ticket_id"]
        while r.status_code == 202:
            time.sleep(2)
            r = client.get(f"{BASE}/api/queue/ticket/{ticket}")
    r.raise_for_status()
    return r.json()


def score(client: httpx.Client, row: dict) -> dict | None:
    for attempt in range(MAX_TRIES):
        try:
            d = analyse(client, row["text"])
            return {
                "key": key(row),
                **{k: row[k] for k in KEPT if k in row},
                "overall": d["overall_score"],
                "verdict": d["overall_verdict"],
                "engines": {e["engine_name"]: e["score"] for e in d["engine_results"]},
            }
        except (httpx.HTTPError, KeyError) as error:
            print(f"  {row['id']}: {error!r} (attempt {attempt + 1})", flush=True)
            time.sleep(5 * (attempt + 1))
    return None


def main() -> None:
    out = Path(sys.argv[1])
    done = {json.loads(line)["key"] for line in out.read_text().splitlines() if line.strip()} if out.exists() else set()
    todo = [row for row in samples() if key(row) not in done]
    print(f"{len(done)} already scored, {len(todo)} to go", flush=True)
    started = time.time()
    with httpx.Client(timeout=600) as client, ThreadPoolExecutor(WORKERS) as pool, out.open("a") as f:
        for i, result in enumerate(pool.map(lambda row: score(client, row), todo), 1):
            if result:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()
            if i % 25 == 0:
                rate = i / (time.time() - started)
                print(f"{i}/{len(todo)} scored, ~{(len(todo) - i) / rate / 60:.0f} min left", flush=True)
    print("done; failed samples are retried by running again", flush=True)


if __name__ == "__main__":
    main()
