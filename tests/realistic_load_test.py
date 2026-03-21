"""
SlopTotal Realistic User Simulation
=====================================
Simulates actual Chrome extension usage patterns to find capacity limits.

User behavior model:
  1. User opens Google, searches → extension fires snippet batch (10 results)
  2. User reads results for 2-8s (think time)
  3. User clicks a result → extension fires quick-score on that page
  4. User reads page for 5-15s, maybe searches again
  5. Occasionally (10% chance) user triggers a full analysis from the web UI

UX thresholds:
  - Snippet badges must appear < 2000ms (user is scanning results)
  - Quick-score must respond < 1000ms (user just landed on page)
  - Full analysis can take up to 30s (user expects to wait)

Ramps from 5 → 10 → 20 → 30 → 50 concurrent users.
Each "user" runs a 30-second browsing session.
Aborts if system health degrades.
"""

import asyncio
import time
import random
import statistics
import json
import os
import sys
from dataclasses import dataclass, field

import httpx
import psutil

BASE_URL = os.getenv("SLOPTOTAL_URL", "http://localhost:8000")

MAX_CPU_PERCENT = 85.0
MIN_AVAIL_RAM_GB = 10.0

# --- Realistic text corpus ---

HUMAN_TEXTS = [
    "The city council voted unanimously to approve the new park renovation project after months of public hearings and community feedback sessions.",
    "My grandmother's recipe for apple pie uses a mix of Granny Smith and Honeycrisp apples with a hint of cardamom that makes it unlike anything you've ever tasted.",
    "The research team published findings showing that sleep deprivation affects memory consolidation differently in adolescents compared to adults over 50.",
    "We drove along the coast for three hours before finding a small fishing village where locals served the freshest ceviche I've ever had.",
    "The quarterback threw a 40-yard pass in the final seconds to tie the game, sending it into overtime for the third time this season.",
    "After debugging for six hours, I discovered the issue was a single missing semicolon in line 847 of the configuration parser module.",
    "The museum's new exhibit features interactive displays that let visitors experience what daily life was like in ancient Pompeii before the eruption.",
    "Property values in the neighborhood have increased by 23 percent since the new transit line was approved, pricing out many longtime residents.",
    "The documentary follows three families over five years as they navigate the foster care system, revealing both its failures and unexpected moments of grace.",
    "Local farmers reported that this year's drought has reduced wheat yields by nearly 40 percent, the worst harvest in two decades.",
]

AI_TEXTS = [
    "In the rapidly evolving landscape of artificial intelligence, researchers continue to push the boundaries of what machine learning systems can achieve. The integration of transformer architectures with reinforcement learning has opened new possibilities for autonomous decision-making systems that can adapt to complex environments.",
    "The implementation of sustainable development practices requires a multifaceted approach that encompasses economic, environmental, and social dimensions. Organizations must leverage innovative technologies while maintaining a commitment to ethical governance frameworks.",
    "Understanding the fundamental principles of quantum computing necessitates a paradigm shift in how we conceptualize information processing. Unlike classical bits, quantum bits exist in superposition states that enable exponentially parallel computations.",
    "The intersection of blockchain technology and decentralized finance represents a transformative shift in how financial transactions are conducted. Smart contracts enable trustless interactions between parties without intermediaries.",
    "Effective leadership in the modern workplace requires emotional intelligence, adaptability, and a commitment to fostering inclusive environments where diverse perspectives are valued and integrated into decision-making processes.",
]

def random_snippet_batch():
    """Generate a realistic batch of 10 Google search snippets."""
    snippets = []
    for i in range(10):
        if random.random() < 0.3:
            text = random.choice(AI_TEXTS)[:180]
        else:
            text = random.choice(HUMAN_TEXTS)[:180]
        snippets.append({
            "id": f"r{i}_{random.randint(1000,9999)}",
            "text": text,
            "url": f"https://example.com/result/{random.randint(1,10000)}",
        })
    return snippets

def random_page_text():
    """Simulate text extracted from a clicked search result."""
    if random.random() < 0.4:
        return random.choice(AI_TEXTS)
    return random.choice(HUMAN_TEXTS) + " " + random.choice(HUMAN_TEXTS)

def random_full_text():
    """Longer text for full analysis."""
    parts = random.choices(HUMAN_TEXTS + AI_TEXTS, k=4)
    return " ".join(parts)


@dataclass
class RequestLog:
    endpoint: str
    latency_ms: float
    status: int
    user_id: int
    timestamp: float


@dataclass
class ScenarioResult:
    num_users: int
    duration_s: float
    requests: list[RequestLog] = field(default_factory=list)
    errors: int = 0
    system_before: dict = field(default_factory=dict)
    system_after: dict = field(default_factory=dict)


def system_snapshot() -> dict:
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    load1, _, _ = os.getloadavg()
    return {
        "cpu_percent": round(cpu, 1),
        "ram_used_gb": round(mem.used / (1024**3), 1),
        "ram_avail_gb": round(mem.available / (1024**3), 1),
        "load_1m": round(load1, 2),
    }


def is_safe() -> tuple[bool, str]:
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    avail_gb = mem.available / (1024 ** 3)
    if cpu > MAX_CPU_PERCENT:
        return False, f"CPU {cpu:.1f}% exceeds {MAX_CPU_PERCENT}%"
    if avail_gb < MIN_AVAIL_RAM_GB:
        return False, f"RAM {avail_gb:.1f}GB below {MIN_AVAIL_RAM_GB}GB"
    return True, "ok"


async def simulate_user(user_id: int, client: httpx.AsyncClient,
                        results: list[RequestLog], session_duration: float,
                        error_counter: list):
    """Simulate one user's browsing session."""
    session_end = time.perf_counter() + session_duration

    # Stagger start: users don't all arrive at once
    await asyncio.sleep(random.uniform(0, session_duration * 0.3))

    while time.perf_counter() < session_end:
        try:
            # Step 1: User searches Google → snippet batch
            t0 = time.perf_counter()
            resp = await client.post(
                f"{BASE_URL}/api/scan/snippets",
                json={"snippets": random_snippet_batch()},
            )
            lat = (time.perf_counter() - t0) * 1000
            results.append(RequestLog("snippets", lat, resp.status_code, user_id, time.time()))

            # Step 2: Think time — user reads search results
            await asyncio.sleep(random.uniform(2.0, 6.0))
            if time.perf_counter() >= session_end:
                break

            # Step 3: User clicks a result → quick-score
            t0 = time.perf_counter()
            resp = await client.post(
                f"{BASE_URL}/api/quick-score",
                json={"text": random_page_text()},
            )
            lat = (time.perf_counter() - t0) * 1000
            results.append(RequestLog("quick-score", lat, resp.status_code, user_id, time.time()))

            # Step 4: Think time — user reads the page
            await asyncio.sleep(random.uniform(4.0, 12.0))
            if time.perf_counter() >= session_end:
                break

            # Step 5: 10% chance user triggers full analysis
            if random.random() < 0.10:
                t0 = time.perf_counter()
                resp = await client.post(
                    f"{BASE_URL}/api/analyze",
                    json={"text": random_full_text()},
                )
                lat = (time.perf_counter() - t0) * 1000
                results.append(RequestLog("full-analyze", lat, resp.status_code, user_id, time.time()))

        except Exception as e:
            error_counter.append(str(e))
            await asyncio.sleep(1.0)


async def run_scenario(num_users: int, session_duration: float = 30.0) -> ScenarioResult:
    """Run a single scenario with N concurrent users."""
    result = ScenarioResult(num_users=num_users, duration_s=session_duration)
    result.system_before = system_snapshot()
    requests: list[RequestLog] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        tasks = [
            simulate_user(i, client, requests, session_duration, errors)
            for i in range(num_users)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    result.requests = requests
    result.errors = len(errors)
    result.system_after = system_snapshot()
    return result


def analyze_scenario(result: ScenarioResult) -> dict:
    """Produce statistics from a scenario run."""
    by_endpoint: dict[str, list[float]] = {}
    status_counts: dict[str, dict[int, int]] = {}
    for r in result.requests:
        by_endpoint.setdefault(r.endpoint, []).append(r.latency_ms)
        status_counts.setdefault(r.endpoint, {})
        status_counts[r.endpoint][r.status] = status_counts[r.endpoint].get(r.status, 0) + 1

    def stats(lats: list[float]) -> dict:
        if not lats:
            return {}
        s = sorted(lats)
        return {
            "count": len(s),
            "min_ms": round(min(s)),
            "mean_ms": round(statistics.mean(s)),
            "p50_ms": round(statistics.median(s)),
            "p90_ms": round(s[int(len(s) * 0.9)]),
            "p95_ms": round(s[int(len(s) * 0.95)]),
            "p99_ms": round(s[int(len(s) * 0.99)]) if len(s) >= 10 else round(max(s)),
            "max_ms": round(max(s)),
        }

    # UX pass/fail
    snippet_lats = by_endpoint.get("snippets", [])
    quick_lats = by_endpoint.get("quick-score", [])
    snippet_p95 = sorted(snippet_lats)[int(len(snippet_lats) * 0.95)] if len(snippet_lats) > 1 else 0
    quick_p95 = sorted(quick_lats)[int(len(quick_lats) * 0.95)] if len(quick_lats) > 1 else 0

    # Throughput
    if result.requests:
        first_ts = min(r.timestamp for r in result.requests)
        last_ts = max(r.timestamp for r in result.requests)
        wall_time = max(last_ts - first_ts, 0.1)
        rps = len(result.requests) / wall_time
    else:
        rps = 0

    return {
        "users": result.num_users,
        "total_requests": len(result.requests),
        "errors": result.errors,
        "requests_per_second": round(rps, 2),
        "endpoints": {ep: stats(lats) for ep, lats in by_endpoint.items()},
        "status_codes": status_counts,
        "ux_verdict": {
            "snippets_p95_ms": round(snippet_p95),
            "snippets_ok": snippet_p95 < 2000,
            "quick_score_p95_ms": round(quick_p95),
            "quick_score_ok": quick_p95 < 1000,
        },
        "system_before": result.system_before,
        "system_after": result.system_after,
    }


def print_scenario(analysis: dict):
    u = analysis["users"]
    print(f"\n{'─' * 60}")
    print(f"  {u} concurrent users  |  {analysis['total_requests']} requests  |  "
          f"{analysis['requests_per_second']} req/s  |  {analysis['errors']} errors")
    print(f"{'─' * 60}")

    for ep, st in analysis["endpoints"].items():
        if not st:
            continue
        print(f"  {ep:15s}  n={st['count']:3d}  "
              f"mean={st['mean_ms']:5d}ms  p50={st['p50_ms']:5d}ms  "
              f"p95={st['p95_ms']:5d}ms  max={st['max_ms']:5d}ms")

    ux = analysis["ux_verdict"]
    snip_icon = "PASS" if ux["snippets_ok"] else "FAIL"
    quick_icon = "PASS" if ux["quick_score_ok"] else "FAIL"
    print(f"\n  UX: snippets p95={ux['snippets_p95_ms']}ms [{snip_icon} <2000ms]  "
          f"quick-score p95={ux['quick_score_p95_ms']}ms [{quick_icon} <1000ms]")
    print(f"  System: CPU {analysis['system_after']['cpu_percent']}%  "
          f"RAM avail {analysis['system_after']['ram_avail_gb']}GB  "
          f"Load {analysis['system_after']['load_1m']}")


async def main():
    # Verify server
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as c:
        try:
            r = await c.get(f"{BASE_URL}/health")
            r.raise_for_status()
        except Exception as e:
            print(f"FATAL: Server not reachable: {e}")
            sys.exit(1)

    print("=" * 60)
    print("  SlopTotal Realistic User Simulation")
    print("=" * 60)
    print(f"  Server: {BASE_URL}")
    print(f"  System: {system_snapshot()}")
    print(f"  Session: 30s per user, staggered arrivals")
    print(f"  UX budget: snippets <2s, quick-score <1s")

    user_counts = [5, 10, 20, 30, 50]
    all_results = []
    capacity_limit = None

    for num_users in user_counts:
        safe, msg = is_safe()
        if not safe:
            print(f"\n  SAFETY ABORT before {num_users} users: {msg}")
            capacity_limit = f"Aborted at {num_users} users: {msg}"
            break

        print(f"\n  Starting scenario: {num_users} users for 30s...")
        result = await run_scenario(num_users, session_duration=30.0)
        analysis = analyze_scenario(result)
        all_results.append(analysis)
        print_scenario(analysis)

        # Check if UX thresholds are blown
        ux = analysis["ux_verdict"]
        if not ux["snippets_ok"] or not ux["quick_score_ok"]:
            capacity_limit = (
                f"UX degraded at {num_users} users: "
                f"snippets p95={ux['snippets_p95_ms']}ms, "
                f"quick-score p95={ux['quick_score_p95_ms']}ms"
            )
            # Run one more to confirm it's not a fluke? No - stop to be safe.
            print(f"\n  UX THRESHOLD BREACHED — stopping ramp.")
            break

        # Cool-down between scenarios
        print(f"  Cooling down 5s...")
        await asyncio.sleep(5.0)
    else:
        capacity_limit = f"All scenarios passed — {user_counts[-1]} users sustained"

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  CAPACITY FINDING: {capacity_limit}")
    print(f"{'=' * 60}")

    # Scaling summary table
    print(f"\n  {'Users':>5s}  {'Req/s':>6s}  {'Snip p95':>9s}  {'Quick p95':>10s}  {'Errors':>6s}  {'Verdict':>8s}")
    print(f"  {'─'*5}  {'─'*6}  {'─'*9}  {'─'*10}  {'─'*6}  {'─'*8}")
    for a in all_results:
        ux = a["ux_verdict"]
        verdict = "PASS" if (ux["snippets_ok"] and ux["quick_score_ok"]) else "FAIL"
        snip = f"{ux['snippets_p95_ms']}ms"
        quick = f"{ux['quick_score_p95_ms']}ms"
        print(f"  {a['users']:5d}  {a['requests_per_second']:6.1f}  {snip:>9s}  {quick:>10s}  {a['errors']:6d}  {verdict:>8s}")

    # Save full report
    report = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "capacity_finding": capacity_limit,
        "scenarios": all_results,
        "system_final": system_snapshot(),
    }
    path = "/root/sloptotal/tests/realistic_load_report.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Full report: {path}")


if __name__ == "__main__":
    asyncio.run(main())
