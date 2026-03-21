#!/usr/bin/env python3
"""Benchmark snippet scan performance — simulates extension workload."""

import asyncio
import time
import httpx
import statistics

API = "http://localhost:8000"

# Realistic snippets: mix of lengths, AI and human text
SNIPPETS = [
    # Short Google snippets (~100-200 chars)
    "Climate change is one of the most pressing issues facing humanity today. Rising global temperatures are causing widespread environmental disruption.",
    "just got back from the dentist and my mouth is completely numb lol. tried to drink coffee and it went everywhere",
    "The Supreme Court ruled 6-3 that the regulation exceeded congressional authority under the Commerce Clause, marking a significant shift.",
    "Machine learning has revolutionized how we approach complex problems. By leveraging large datasets, these systems identify patterns impossible for humans.",
    "PSA if you're getting the SSL cert error after updating, clear your local cert cache. Took me 2 hours to figure that out smh.",
    "Effective communication is essential in any professional setting. Active listening, empathy, and adaptability are key components.",
    "honestly the new season is kinda mid. they completely butchered the storyline and the pacing feels way off compared to the books",
    "The mitochondrial electron transport chain consists of four major protein complexes embedded in the inner mitochondrial membrane.",
    "Quantum computing represents a paradigm shift in computational power, utilizing qubits in superposition states for exponential speedup.",
    "My grandmother used to make this exact dish every Sunday. The secret ingredient is real saffron, not the powdered stuff from stores.",
    # Longer LinkedIn-style posts (~300-600 chars)
    "I'm thrilled to announce that after 3 years of dedicated research, our team has published groundbreaking findings on neural network optimization. This work demonstrates a 40% improvement in training efficiency through novel gradient accumulation techniques. Special thanks to my incredible colleagues who made this possible. The paper is now available on arXiv for anyone interested in advancing the field of deep learning.",
    "Here are five tips for improving your productivity that I've learned over 15 years in tech. First, prioritize ruthlessly using the Eisenhower Matrix. Second, eliminate distractions by blocking social media during deep work. Third, use the Pomodoro Technique for sustained focus. Fourth, batch similar tasks together. Fifth, end each day by planning tomorrow.",
    "The Board of Directors reviewed quarterly financials noting revenue increased 12% year-over-year, driven by Asia-Pacific expansion. Operating margins improved to 18.3%, reflecting ongoing cost optimization and favorable currency effects. We remain optimistic about growth trajectory.",
    "Unpopular opinion but remote work has been terrible for junior developers. You miss out on so much osmotic learning just by sitting near senior engineers. The mentorship gap is real and no amount of Slack messages can replace overhearing how someone debugs a production issue.",
    "We investigated optical properties of quantum dots synthesized via modified hot-injection. TEM revealed uniform 4.2nm particles with 0.3nm std dev. Photoluminescence showed narrow 620nm emission, FWHM 28nm, confirming excellent size uniformity.",
]


async def warm_up(client: httpx.AsyncClient):
    """Warm up models with a single request."""
    print("Warming up models...")
    t0 = time.perf_counter()
    resp = await client.post(f"{API}/api/scan/snippets", json={
        "snippets": [{"id": "warmup", "text": SNIPPETS[0]}]
    }, timeout=60)
    ms = round((time.perf_counter() - t0) * 1000)
    print(f"  Warmup: {ms}ms (status={resp.status_code})\n")


async def bench_single_batch(client: httpx.AsyncClient, n: int, label: str):
    """Benchmark a single batch of N snippets."""
    snippets = [{"id": f"s{i}", "text": SNIPPETS[i % len(SNIPPETS)]} for i in range(n)]
    total_chars = sum(len(s["text"]) for s in snippets)

    times = []
    for run in range(3):
        t0 = time.perf_counter()
        resp = await client.post(f"{API}/api/scan/snippets", json={"snippets": snippets}, timeout=60)
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)
        data = resp.json()
        timing = data.get("timing", {})
        if run == 0:
            print(f"  {label}: server={timing.get('total_ms','?')}ms "
                  f"(e5={timing.get('e5_ms','?')}ms fakespot={timing.get('fakespot_ms','?')}ms)")

    avg = statistics.mean(times)
    mn = min(times)
    mx = max(times)
    per_snippet = avg / n
    print(f"  {label}: {n} snippets, {total_chars} chars | "
          f"avg={avg:.0f}ms min={mn:.0f}ms max={mx:.0f}ms | "
          f"{per_snippet:.0f}ms/snippet")
    return avg


async def bench_sub_batches(client: httpx.AsyncClient, total: int, batch_size: int, label: str):
    """Benchmark concurrent sub-batches (simulates extension behavior)."""
    all_snippets = [{"id": f"sb{i}", "text": SNIPPETS[i % len(SNIPPETS)]} for i in range(total)]
    batches = [all_snippets[i:i+batch_size] for i in range(0, len(all_snippets), batch_size)]
    total_chars = sum(len(s["text"]) for s in all_snippets)

    async def send_batch(snippets, idx):
        t0 = time.perf_counter()
        resp = await client.post(f"{API}/api/scan/snippets", json={"snippets": snippets}, timeout=60)
        elapsed = (time.perf_counter() - t0) * 1000
        data = resp.json()
        timing = data.get("timing", {})
        return idx, elapsed, timing

    times_total = []
    for run in range(3):
        t0 = time.perf_counter()
        results = await asyncio.gather(*[send_batch(b, i) for i, b in enumerate(batches)])
        wall_time = (time.perf_counter() - t0) * 1000
        times_total.append(wall_time)

        if run == 0:
            first_done = min(r[1] for r in results)
            last_done = max(r[1] for r in results)
            print(f"  {label}: first result at {first_done:.0f}ms, all done at {wall_time:.0f}ms")
            for idx, elapsed, timing in sorted(results, key=lambda r: r[0]):
                print(f"    batch[{idx}]: {elapsed:.0f}ms "
                      f"(server={timing.get('total_ms','?')}ms "
                      f"e5={timing.get('e5_ms','?')}ms "
                      f"fakespot={timing.get('fakespot_ms','?')}ms "
                      f"chars={timing.get('total_chars','?')})")

    avg = statistics.mean(times_total)
    mn = min(times_total)
    first_avg = statistics.mean([min(r[1] for r in await asyncio.gather(*[send_batch(b, i) for i, b in enumerate(batches)])) for _ in range(1)]) if False else min(r[1] for r in results)
    print(f"  {label}: {total} snippets in {len(batches)}x{batch_size} batches, {total_chars} chars | "
          f"wall avg={avg:.0f}ms min={mn:.0f}ms | "
          f"first batch ~{min(r[1] for r in results):.0f}ms")
    return avg


async def main():
    async with httpx.AsyncClient() as client:
        # Check server
        resp = await client.get(f"{API}/health", timeout=5)
        h = resp.json()
        print(f"Server: {h['status']} | {h['engines']} engines\n")

        await warm_up(client)

        # --- Single batch benchmarks ---
        print("=" * 70)
        print("SINGLE BATCH (one API call)")
        print("=" * 70)
        await bench_single_batch(client, 1, "1 snippet")
        await bench_single_batch(client, 3, "3 snippets")
        await bench_single_batch(client, 5, "5 snippets")
        await bench_single_batch(client, 10, "10 snippets")
        await bench_single_batch(client, 15, "15 snippets")

        # --- Sub-batch benchmarks (simulates extension) ---
        print()
        print("=" * 70)
        print("SUB-BATCHES (parallel API calls — simulates extension)")
        print("=" * 70)
        await bench_sub_batches(client, 10, 5, "10 in 2x5")
        print()
        await bench_sub_batches(client, 15, 5, "15 in 3x5")
        print()
        await bench_sub_batches(client, 15, 15, "15 in 1x15 (old)")

        # --- Comparison ---
        print()
        print("=" * 70)
        print("KEY COMPARISON: 15 snippets")
        print("=" * 70)
        old = await bench_single_batch(client, 15, "old (1x15)")
        print()
        new = await bench_sub_batches(client, 15, 5, "new (3x5)")
        if old > 0:
            print(f"\n  Speedup: wall time {old/new:.1f}x faster with sub-batching")


if __name__ == "__main__":
    asyncio.run(main())
