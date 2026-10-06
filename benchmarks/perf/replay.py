"""Replay production-shaped full-analysis traffic against a running instance.

Requests arrive as a Poisson process at RATE per minute for MINUTES minutes;
each text's length is drawn from the word counts of real production scans,
and its words from SlopBench texts, so that no two requests share a cache
entry. For every request it records the time from submission to the finished
report, then prints p50/p90/max by length band.

Run the instance with SLOPTOTAL_CACHE_ENABLED=false and the production
settings, then:

  python benchmarks/perf/replay.py lengths.json RATE MINUTES out.json
"""

import asyncio
import json
import random
import sys
import time
from pathlib import Path
from statistics import median

import httpx

BASE = "http://127.0.0.1:8012"
CORPUS = Path(__file__).parents[2] / "tests/eval/slopbench/corpus"
BANDS = [(0, 300), (300, 1000), (1000, 3000), (3000, 10**9)]


def word_pool() -> list[str]:
    words: list[str] = []
    for path in sorted(CORPUS.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                words += json.loads(line)["text"].split()
    return words


def make_text(pool: list[str], words: int, rng: random.Random) -> str:
    start = rng.randrange(len(pool) - words - 1)
    return " ".join(pool[start : start + words])


async def one(client: httpx.AsyncClient, text: str) -> float:
    started = time.perf_counter()
    r = await client.post(f"{BASE}/api/analyze", json={"text": text})
    while r.status_code == 429:
        await asyncio.sleep(2)
        r = await client.post(f"{BASE}/api/analyze", json={"text": text})
    if r.status_code == 202:
        ticket = r.json()["ticket_id"]
        while r.status_code == 202:
            await asyncio.sleep(1)
            r = await client.get(f"{BASE}/api/queue/ticket/{ticket}")
    r.raise_for_status()
    return time.perf_counter() - started


async def main() -> None:
    lengths = [n for n in json.load(open(sys.argv[1])) if n >= 20]
    rate, minutes, out = float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    rng = random.Random(0)
    pool = word_pool()
    plan, t = [], rng.expovariate(rate / 60)
    while t < minutes * 60:
        plan.append((t, min(rng.choice(lengths), len(pool) // 2)))
        t += rng.expovariate(rate / 60)

    results = []
    async with httpx.AsyncClient(timeout=900) as client:
        began = time.perf_counter()

        async def fire(at: float, words: int) -> None:
            await asyncio.sleep(max(0.0, at - (time.perf_counter() - began)))
            text = make_text(pool, words, rng)
            try:
                seconds = await one(client, text)
                results.append({"words": words, "seconds": round(seconds, 2)})
            except httpx.HTTPError as error:
                results.append({"words": words, "error": repr(error)})

        await asyncio.gather(*(fire(at, words) for at, words in plan))

    json.dump(results, open(out, "w"))
    done = [r for r in results if "seconds" in r]
    print(f"{len(plan)} requests at {rate}/min for {minutes} min, {len(results) - len(done)} errors")
    print("| Words | n | p50 s | p90 s | max s |")
    print("|---|---|---|---|---|")
    for lo, hi in BANDS:
        s = sorted(r["seconds"] for r in done if lo <= r["words"] < hi)
        if s:
            print(f"| {lo}-{hi if hi < 10**9 else ''} | {len(s)} | {median(s):.1f} | {s[int(len(s) * 0.9)]:.1f} | {s[-1]:.1f} |")


if __name__ == "__main__":
    asyncio.run(main())
