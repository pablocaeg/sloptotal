"""
SlopTotal Concurrency Load Test Suite
======================================
Safe, incremental load tests that monitor system health throughout.
Aborts if CPU > 85% or available RAM < 10GB.

Tests:
  1. Baseline single-request latency (snippet, quick-score, full)
  2. Concurrent snippet batches (ramp 1→4)
  3. Concurrent quick-score requests (ramp 1→4)
  4. Mixed workload: snippets + quick-score + full analysis
  5. Backpressure / 429 test for full analyses
"""

import asyncio
import time
import statistics
import json
import sys
import os

import httpx
import psutil

BASE_URL = os.getenv("SLOPTOTAL_URL", "http://localhost:8000")

# Safety thresholds
MAX_CPU_PERCENT = 85.0
MIN_AVAIL_RAM_GB = 10.0

# Sample texts for testing
HUMAN_SNIPPET = (
    "The quick brown fox jumps over the lazy dog near the riverbank. "
    "Morning dew glistened on the grass as birds sang their familiar songs."
)

AI_TEXT = (
    "Artificial intelligence has revolutionized the way we approach complex problems "
    "in modern society. Through the utilization of sophisticated machine learning algorithms "
    "and neural network architectures, researchers have been able to achieve unprecedented "
    "levels of accuracy in tasks ranging from natural language processing to computer vision. "
    "Furthermore, the integration of these technologies into everyday applications has "
    "fundamentally transformed how individuals interact with digital systems."
)

SNIPPETS_10 = [
    {"id": f"s{i}", "text": f"Result {i}: {HUMAN_SNIPPET}" if i % 2 == 0
     else f"Result {i}: {AI_TEXT[:120]}", "url": f"https://example.com/{i}"}
    for i in range(10)
]


class SafetyMonitor:
    """Abort tests if system resources are stressed."""

    def check(self) -> tuple[bool, str]:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        avail_gb = mem.available / (1024 ** 3)

        if cpu > MAX_CPU_PERCENT:
            return False, f"CPU at {cpu:.1f}% (limit {MAX_CPU_PERCENT}%)"
        if avail_gb < MIN_AVAIL_RAM_GB:
            return False, f"Available RAM {avail_gb:.1f}GB (limit {MIN_AVAIL_RAM_GB}GB)"
        return True, f"CPU {cpu:.1f}%, RAM avail {avail_gb:.1f}GB"

    def snapshot(self) -> dict:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        load1, load5, load15 = os.getloadavg()
        return {
            "cpu_percent": round(cpu, 1),
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_avail_gb": round(mem.available / (1024**3), 1),
            "load_1m": round(load1, 2),
        }


monitor = SafetyMonitor()


def fmt_ms(ms: float) -> str:
    return f"{ms:.0f}ms"


def fmt_stats(latencies: list[float]) -> dict:
    if not latencies:
        return {"count": 0}
    return {
        "count": len(latencies),
        "min": fmt_ms(min(latencies)),
        "p50": fmt_ms(statistics.median(latencies)),
        "p90": fmt_ms(sorted(latencies)[int(len(latencies) * 0.9)]),
        "p99": fmt_ms(sorted(latencies)[int(len(latencies) * 0.99)]) if len(latencies) >= 10 else "n/a",
        "max": fmt_ms(max(latencies)),
        "mean": fmt_ms(statistics.mean(latencies)),
    }


async def timed_request(client: httpx.AsyncClient, method: str, url: str,
                        **kwargs) -> tuple[float, int, dict | None]:
    """Returns (latency_ms, status_code, response_json)."""
    start = time.perf_counter()
    resp = await client.request(method, url, **kwargs)
    elapsed = (time.perf_counter() - start) * 1000
    try:
        body = resp.json()
    except Exception:
        body = None
    return elapsed, resp.status_code, body


# ─── Test 1: Baseline single-request latency ───

async def test_baseline(client: httpx.AsyncClient) -> dict:
    """Single request to each endpoint type, repeated 3x for warm measurement."""
    results = {}

    # Snippet batch (10 items)
    lats = []
    for _ in range(3):
        ms, status, body = await timed_request(
            client, "POST", f"{BASE_URL}/api/scan/snippets",
            json={"snippets": SNIPPETS_10},
        )
        if status == 200:
            lats.append(ms)
    results["snippet_batch_10"] = fmt_stats(lats)

    # Quick score
    lats = []
    for _ in range(3):
        ms, status, body = await timed_request(
            client, "POST", f"{BASE_URL}/api/quick-score",
            json={"text": AI_TEXT},
        )
        if status == 200:
            lats.append(ms)
    results["quick_score"] = fmt_stats(lats)

    return results


# ─── Test 2: Concurrent snippet batches ───

async def test_concurrent_snippets(client: httpx.AsyncClient) -> dict:
    results = {}

    for concurrency in [1, 2, 3, 4]:
        safe, msg = monitor.check()
        if not safe:
            results[f"c{concurrency}"] = {"skipped": msg}
            break

        lats = []

        async def one_batch():
            ms, status, body = await timed_request(
                client, "POST", f"{BASE_URL}/api/scan/snippets",
                json={"snippets": SNIPPETS_10},
            )
            if status == 200:
                lats.append(ms)
                return body.get("elapsed_ms") if body else None
            return None

        # Run 2 rounds at each concurrency level
        for _ in range(2):
            tasks = [one_batch() for _ in range(concurrency)]
            await asyncio.gather(*tasks)
            await asyncio.sleep(0.5)  # breathing room

        results[f"c{concurrency}"] = {
            **fmt_stats(lats),
            "system": monitor.snapshot(),
        }

    return results


# ─── Test 3: Concurrent quick-score ───

async def test_concurrent_quick(client: httpx.AsyncClient) -> dict:
    results = {}

    for concurrency in [1, 2, 3, 4]:
        safe, msg = monitor.check()
        if not safe:
            results[f"c{concurrency}"] = {"skipped": msg}
            break

        lats = []

        async def one_req():
            ms, status, body = await timed_request(
                client, "POST", f"{BASE_URL}/api/quick-score",
                json={"text": AI_TEXT},
            )
            if status == 200:
                lats.append(ms)

        for _ in range(2):
            tasks = [one_req() for _ in range(concurrency)]
            await asyncio.gather(*tasks)
            await asyncio.sleep(0.5)

        results[f"c{concurrency}"] = {
            **fmt_stats(lats),
            "system": monitor.snapshot(),
        }

    return results


# ─── Test 4: Mixed workload ───

async def test_mixed_workload(client: httpx.AsyncClient) -> dict:
    """Simulate real usage: 2 snippet batches + 2 quick-scores simultaneously."""
    safe, msg = monitor.check()
    if not safe:
        return {"skipped": msg}

    snippet_lats = []
    quick_lats = []

    async def snippet_batch():
        ms, status, _ = await timed_request(
            client, "POST", f"{BASE_URL}/api/scan/snippets",
            json={"snippets": SNIPPETS_10},
        )
        if status == 200:
            snippet_lats.append(ms)

    async def quick_score():
        ms, status, _ = await timed_request(
            client, "POST", f"{BASE_URL}/api/quick-score",
            json={"text": AI_TEXT},
        )
        if status == 200:
            quick_lats.append(ms)

    # 3 rounds of mixed load
    for _ in range(3):
        safe, msg = monitor.check()
        if not safe:
            break
        tasks = [snippet_batch(), snippet_batch(), quick_score(), quick_score()]
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.5)

    return {
        "snippet_batches": fmt_stats(snippet_lats),
        "quick_scores": fmt_stats(quick_lats),
        "system": monitor.snapshot(),
    }


# ─── Test 5: Backpressure / 429 test ───

async def test_backpressure(client: httpx.AsyncClient) -> dict:
    """Fire multiple full analyses to trigger the concurrency guard."""
    safe, msg = monitor.check()
    if not safe:
        return {"skipped": msg}

    statuses = []

    async def full_analysis():
        ms, status, body = await timed_request(
            client, "POST", f"{BASE_URL}/api/analyze",
            json={"text": AI_TEXT},
            timeout=120.0,
        )
        statuses.append(status)
        return status, ms, body

    # Fire 4 full analyses concurrently (limit is 2)
    tasks = [full_analysis() for _ in range(4)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ok_count = sum(1 for s in statuses if s == 200)
    rejected_count = sum(1 for s in statuses if s == 429)
    other = [s for s in statuses if s not in (200, 429)]

    return {
        "total_requests": len(statuses),
        "http_200": ok_count,
        "http_429": rejected_count,
        "other_statuses": other,
        "backpressure_working": rejected_count > 0,
        "system": monitor.snapshot(),
    }


# ─── Main runner ───

async def main():
    report = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": BASE_URL,
        "system_before": monitor.snapshot(),
        "tests": {},
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        # Verify server is up
        try:
            resp = await client.get(f"{BASE_URL}/health")
            health = resp.json()
            report["server_health"] = health
        except Exception as e:
            print(f"FATAL: Server not reachable at {BASE_URL}: {e}")
            sys.exit(1)

        print("=" * 64)
        print("  SlopTotal Concurrency Load Test")
        print("=" * 64)
        print(f"  Server: {BASE_URL}")
        print(f"  System: {report['system_before']}")
        print()

        # Test 1
        print("[1/5] Baseline single-request latency...")
        report["tests"]["1_baseline"] = await test_baseline(client)
        print(f"       Snippet batch: {report['tests']['1_baseline']['snippet_batch_10']}")
        print(f"       Quick score:   {report['tests']['1_baseline']['quick_score']}")
        print()

        # Test 2
        print("[2/5] Concurrent snippet batches (ramp 1→4)...")
        report["tests"]["2_concurrent_snippets"] = await test_concurrent_snippets(client)
        for k, v in report["tests"]["2_concurrent_snippets"].items():
            label = f"       {k}: "
            if "skipped" in v:
                print(f"{label}SKIPPED ({v['skipped']})")
            else:
                print(f"{label}{v.get('mean', '?')} mean, {v.get('p90', '?')} p90")
        print()

        # Test 3
        print("[3/5] Concurrent quick-score (ramp 1→4)...")
        report["tests"]["3_concurrent_quick"] = await test_concurrent_quick(client)
        for k, v in report["tests"]["3_concurrent_quick"].items():
            label = f"       {k}: "
            if "skipped" in v:
                print(f"{label}SKIPPED ({v['skipped']})")
            else:
                print(f"{label}{v.get('mean', '?')} mean, {v.get('p90', '?')} p90")
        print()

        # Test 4
        print("[4/5] Mixed workload (snippets + quick-score)...")
        report["tests"]["4_mixed_workload"] = await test_mixed_workload(client)
        mw = report["tests"]["4_mixed_workload"]
        if "skipped" in mw:
            print(f"       SKIPPED ({mw['skipped']})")
        else:
            print(f"       Snippet batches: {mw['snippet_batches'].get('mean', '?')} mean")
            print(f"       Quick scores:    {mw['quick_scores'].get('mean', '?')} mean")
        print()

        # Test 5
        print("[5/5] Backpressure / 429 test (4 concurrent full analyses)...")
        report["tests"]["5_backpressure"] = await test_backpressure(client)
        bp = report["tests"]["5_backpressure"]
        if "skipped" in bp:
            print(f"       SKIPPED ({bp['skipped']})")
        else:
            print(f"       200s: {bp['http_200']}, 429s: {bp['http_429']}, "
                  f"backpressure working: {bp['backpressure_working']}")
        print()

    report["system_after"] = monitor.snapshot()

    print("=" * 64)
    print("  Test Complete")
    print(f"  System after: {report['system_after']}")
    print("=" * 64)

    # Save full report
    report_path = "/root/sloptotal/tests/load_test_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to {report_path}")

    return report


if __name__ == "__main__":
    asyncio.run(main())
