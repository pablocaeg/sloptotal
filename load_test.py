#!/usr/bin/env python3
"""
Load testing script for SlopTotal API.

Usage:
    python load_test.py [--url URL] [--concurrent N] [--requests N] [--test TYPE]

Examples:
    python load_test.py --concurrent 10 --requests 50
    python load_test.py --test cache --concurrent 20
    python load_test.py --test urls --concurrent 5 --requests 10
"""

import argparse
import asyncio
import random
import statistics
import time
from dataclasses import dataclass, field

import httpx

# Sample texts of varying lengths for testing
SAMPLE_TEXTS = [
    # Short AI-like text
    """In conclusion, it is important to note that the implementation of sustainable practices
    requires a multifaceted approach. Furthermore, stakeholders must collaborate effectively
    to achieve optimal outcomes. This comprehensive strategy ensures long-term success.""",

    # Medium human-like text
    """I was walking down the street yesterday when I saw the most bizarre thing - a guy
    juggling flaming torches while riding a unicycle. No joke! People were just walking
    past like it was totally normal. Maybe I'm the weird one for stopping to watch?
    Anyway, made my whole day. Sometimes city life surprises you.""",

    # Longer mixed text
    """The development of artificial intelligence has progressed rapidly in recent years,
    leading to significant advances in natural language processing. However, I think we
    often forget the human element in all this tech stuff. My grandmother asked me the
    other day what ChatGPT was, and honestly? Explaining it was harder than I thought.
    She kept asking "but how does it KNOW things?" and I realized I didn't have a great
    answer. The intersection of technology and human understanding remains a fascinating
    area of study, with implications for education, communication, and society at large.""",

    # Technical text
    """The TCP/IP protocol stack consists of four layers: the link layer, internet layer,
    transport layer, and application layer. Each layer has specific responsibilities.
    The transport layer, for instance, handles end-to-end communication and includes
    protocols like TCP and UDP. TCP provides reliable, ordered delivery of data streams,
    while UDP offers a simpler, connectionless service. Understanding these protocols
    is essential for network programming and troubleshooting connectivity issues.""",

    # News-style text
    """Local authorities announced today that the new community center will open next month,
    following two years of construction delays. The facility includes a gymnasium, swimming
    pool, and meeting rooms available for public use. Mayor Johnson stated that the center
    represents a significant investment in the community's future. Residents can register
    for programs starting Monday. The opening ceremony is scheduled for March 15th.""",
]

# Grokipedia URLs for testing (format: /page/Topic_Name)
TEST_URLS = [
    "https://grokipedia.com/page/New_York_City",
    "https://grokipedia.com/page/Artificial_intelligence",
    "https://grokipedia.com/page/Machine_learning",
    "https://grokipedia.com/page/Quantum_computing",
    "https://grokipedia.com/page/Bitcoin",
    "https://grokipedia.com/page/Climate_change",
    "https://grokipedia.com/page/Space_exploration",
    "https://grokipedia.com/page/Electric_vehicles",
    "https://grokipedia.com/page/Renewable_energy",
    "https://grokipedia.com/page/Cybersecurity",
]


@dataclass
class RequestResult:
    """Result of a single request."""
    success: bool
    duration_ms: float
    status_code: int = 0
    error: str = ""
    cached: bool = False
    report_id: str = ""
    url: str = ""


@dataclass
class LoadTestResults:
    """Aggregated load test results."""
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    cache_hits: int = 0
    durations_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    start_time: float = 0
    end_time: float = 0

    @property
    def total_duration_s(self) -> float:
        return self.end_time - self.start_time

    @property
    def requests_per_second(self) -> float:
        if self.total_duration_s > 0:
            return self.total_requests / self.total_duration_s
        return 0

    @property
    def success_rate(self) -> float:
        if self.total_requests > 0:
            return (self.successful / self.total_requests) * 100
        return 0

    @property
    def avg_duration_ms(self) -> float:
        if self.durations_ms:
            return statistics.mean(self.durations_ms)
        return 0

    @property
    def p50_ms(self) -> float:
        if self.durations_ms:
            return statistics.median(self.durations_ms)
        return 0

    @property
    def p95_ms(self) -> float:
        if len(self.durations_ms) >= 2:
            sorted_d = sorted(self.durations_ms)
            idx = int(len(sorted_d) * 0.95)
            return sorted_d[min(idx, len(sorted_d) - 1)]
        return self.avg_duration_ms

    @property
    def p99_ms(self) -> float:
        if len(self.durations_ms) >= 2:
            sorted_d = sorted(self.durations_ms)
            idx = int(len(sorted_d) * 0.99)
            return sorted_d[min(idx, len(sorted_d) - 1)]
        return self.avg_duration_ms


async def make_text_request(
    client: httpx.AsyncClient,
    base_url: str,
    text: str,
    timeout: float = 120.0,
) -> RequestResult:
    """Make a single text analysis request."""
    start = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url}/api/analyze",
            json={"text": text},
            timeout=timeout,
        )
        duration_ms = (time.perf_counter() - start) * 1000

        if response.status_code == 200:
            data = response.json()
            return RequestResult(
                success=True,
                duration_ms=duration_ms,
                status_code=response.status_code,
                report_id=data.get("id", ""),
                cached=False,
            )
        else:
            return RequestResult(
                success=False,
                duration_ms=duration_ms,
                status_code=response.status_code,
                error=response.text[:200],
            )
    except httpx.TimeoutException:
        duration_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            success=False,
            duration_ms=duration_ms,
            error="Timeout",
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            success=False,
            duration_ms=duration_ms,
            error=str(e),
        )


async def make_url_request(
    client: httpx.AsyncClient,
    base_url: str,
    target_url: str,
    timeout: float = 180.0,
) -> RequestResult:
    """Make a single URL analysis request."""
    start = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url}/api/analyze",
            json={"url": target_url},
            timeout=timeout,
        )
        duration_ms = (time.perf_counter() - start) * 1000

        if response.status_code == 200:
            data = response.json()
            return RequestResult(
                success=True,
                duration_ms=duration_ms,
                status_code=response.status_code,
                report_id=data.get("id", ""),
                url=target_url,
                cached=False,
            )
        else:
            error_text = response.text[:200]
            # Try to extract error message from JSON
            try:
                error_data = response.json()
                error_text = error_data.get("error", error_text)
            except Exception:
                pass
            return RequestResult(
                success=False,
                duration_ms=duration_ms,
                status_code=response.status_code,
                error=error_text,
                url=target_url,
            )
    except httpx.TimeoutException:
        duration_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            success=False,
            duration_ms=duration_ms,
            error="Timeout",
            url=target_url,
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            success=False,
            duration_ms=duration_ms,
            error=str(e),
            url=target_url,
        )


async def make_health_request(
    client: httpx.AsyncClient,
    base_url: str,
) -> RequestResult:
    """Make a health check request."""
    start = time.perf_counter()
    try:
        response = await client.get(f"{base_url}/health", timeout=10.0)
        duration_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            success=response.status_code == 200,
            duration_ms=duration_ms,
            status_code=response.status_code,
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return RequestResult(
            success=False,
            duration_ms=duration_ms,
            error=str(e),
        )


async def run_url_test(
    base_url: str,
    num_concurrent: int,
    num_requests: int,
    urls: list[str],
) -> LoadTestResults:
    """Run load test with URL requests."""
    results = LoadTestResults()
    results.start_time = time.perf_counter()

    semaphore = asyncio.Semaphore(num_concurrent)

    async def bounded_request(url: str, client: httpx.AsyncClient) -> RequestResult:
        async with semaphore:
            return await make_url_request(client, base_url, url)

    # Cycle through URLs if we need more requests than URLs
    test_urls = []
    for i in range(num_requests):
        test_urls.append(urls[i % len(urls)])

    print(f"\nStarting URL load test: {num_requests} requests, {num_concurrent} concurrent")
    print(f"Using {len(set(test_urls))} unique URLs")
    print("-" * 60)

    async with httpx.AsyncClient() as client:
        # First, check health
        health = await make_health_request(client, base_url)
        if not health.success:
            print(f"WARNING: Health check failed: {health.error}")

        # Run all requests
        tasks = [bounded_request(url, client) for url in test_urls]

        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.total_requests += 1
            if result.success:
                results.successful += 1
                results.durations_ms.append(result.duration_ms)
            else:
                results.failed += 1
                results.errors.append(f"{result.url}: {result.error}")

            completed += 1
            if completed % 5 == 0 or completed == num_requests:
                print(f"Progress: {completed}/{num_requests} "
                      f"({results.successful} ok, {results.failed} failed)")

    results.end_time = time.perf_counter()
    return results


async def run_concurrent_test(
    base_url: str,
    num_concurrent: int,
    num_requests: int,
    test_type: str = "unique",
) -> LoadTestResults:
    """Run load test with concurrent requests."""
    results = LoadTestResults()
    results.start_time = time.perf_counter()

    semaphore = asyncio.Semaphore(num_concurrent)

    async def bounded_request(text: str, client: httpx.AsyncClient) -> RequestResult:
        async with semaphore:
            return await make_text_request(client, base_url, text)

    # Prepare texts based on test type
    if test_type == "unique":
        # Each request gets unique text (no cache hits)
        texts = [
            random.choice(SAMPLE_TEXTS) + f"\n\nUnique ID: {i} - {time.time()}"
            for i in range(num_requests)
        ]
    elif test_type == "cache":
        # All requests use same text (test cache performance)
        base_text = SAMPLE_TEXTS[0] + f"\n\nCache test: {time.time()}"
        texts = [base_text] * num_requests
    elif test_type == "mixed":
        # 50% unique, 50% repeated (realistic mix)
        unique_texts = [
            random.choice(SAMPLE_TEXTS) + f"\n\nUnique: {i}"
            for i in range(num_requests // 2)
        ]
        repeated_text = SAMPLE_TEXTS[1] + f"\n\nRepeated: {time.time()}"
        texts = unique_texts + [repeated_text] * (num_requests - len(unique_texts))
        random.shuffle(texts)
    else:
        texts = [random.choice(SAMPLE_TEXTS) for _ in range(num_requests)]

    print(f"\nStarting load test: {num_requests} requests, {num_concurrent} concurrent")
    print(f"Test type: {test_type}")
    print("-" * 60)

    async with httpx.AsyncClient() as client:
        # First, check health
        health = await make_health_request(client, base_url)
        if not health.success:
            print(f"WARNING: Health check failed: {health.error}")

        # Run all requests
        tasks = [bounded_request(text, client) for text in texts]

        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.total_requests += 1
            if result.success:
                results.successful += 1
                results.durations_ms.append(result.duration_ms)
                if result.cached:
                    results.cache_hits += 1
            else:
                results.failed += 1
                results.errors.append(result.error)

            completed += 1
            if completed % 10 == 0 or completed == num_requests:
                print(f"Progress: {completed}/{num_requests} "
                      f"({results.successful} ok, {results.failed} failed)")

    results.end_time = time.perf_counter()
    return results


async def run_ramp_test(
    base_url: str,
    max_concurrent: int,
    requests_per_level: int = 10,
) -> dict[int, LoadTestResults]:
    """Run ramp-up test to find breaking point."""
    print("\n" + "=" * 60)
    print("RAMP-UP TEST")
    print("=" * 60)

    all_results = {}
    levels = [1, 2, 5, 10, 15, 20, max_concurrent]
    levels = [l for l in levels if l <= max_concurrent]
    levels = sorted(set(levels))

    for concurrent in levels:
        print(f"\n--- Testing {concurrent} concurrent requests ---")
        results = await run_concurrent_test(
            base_url,
            num_concurrent=concurrent,
            num_requests=requests_per_level,
            test_type="unique",
        )
        all_results[concurrent] = results

        print(f"  Success rate: {results.success_rate:.1f}%")
        print(f"  Avg latency: {results.avg_duration_ms:.0f}ms")
        print(f"  P95 latency: {results.p95_ms:.0f}ms")
        print(f"  Throughput: {results.requests_per_second:.2f} req/s")

        if results.success_rate < 90:
            print(f"\n  WARNING: Success rate dropped below 90% at {concurrent} concurrent")
            break

        # Brief pause between levels
        await asyncio.sleep(2)

    return all_results


def print_results(results: LoadTestResults):
    """Print formatted test results."""
    print("\n" + "=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)

    print(f"\nRequests:")
    print(f"  Total:      {results.total_requests}")
    print(f"  Successful: {results.successful}")
    print(f"  Failed:     {results.failed}")
    print(f"  Success %:  {results.success_rate:.1f}%")

    if results.cache_hits > 0:
        print(f"  Cache hits: {results.cache_hits}")

    print(f"\nTiming:")
    print(f"  Total duration: {results.total_duration_s:.2f}s")
    print(f"  Throughput:     {results.requests_per_second:.2f} req/s")

    if results.durations_ms:
        print(f"\nLatency (successful requests):")
        print(f"  Min:    {min(results.durations_ms):.0f}ms")
        print(f"  Avg:    {results.avg_duration_ms:.0f}ms")
        print(f"  Median: {results.p50_ms:.0f}ms")
        print(f"  P95:    {results.p95_ms:.0f}ms")
        print(f"  P99:    {results.p99_ms:.0f}ms")
        print(f"  Max:    {max(results.durations_ms):.0f}ms")

    if results.errors:
        unique_errors = list(set(results.errors))[:5]
        print(f"\nErrors (showing up to 5 unique):")
        for err in unique_errors:
            print(f"  - {err[:100]}")


async def main():
    parser = argparse.ArgumentParser(description="Load test SlopTotal API")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of SlopTotal API")
    parser.add_argument("--concurrent", type=int, default=5, help="Concurrent requests")
    parser.add_argument("--requests", type=int, default=20, help="Total requests")
    parser.add_argument(
        "--test",
        choices=["unique", "cache", "mixed", "ramp", "urls"],
        default="unique",
        help="Test type: unique (no cache), cache (same text), mixed, ramp (find limits), urls (test with URLs)",
    )
    args = parser.parse_args()

    print(f"SlopTotal Load Test")
    print(f"Target: {args.url}")

    # Check server is up
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{args.url}/health", timeout=5.0)
            if resp.status_code == 200:
                health = resp.json()
                print(f"Server status: {health.get('status', 'unknown')}")
                print(f"Database: {health.get('database', {}).get('status', 'unknown')}")
            else:
                print(f"WARNING: Health check returned {resp.status_code}")
        except Exception as e:
            print(f"ERROR: Cannot connect to server: {e}")
            print("Make sure the server is running: python -m uvicorn app.main:app")
            return

    if args.test == "ramp":
        await run_ramp_test(args.url, max_concurrent=args.concurrent)
    elif args.test == "urls":
        results = await run_url_test(
            args.url,
            num_concurrent=args.concurrent,
            num_requests=args.requests,
            urls=TEST_URLS,
        )
        print_results(results)
    else:
        results = await run_concurrent_test(
            args.url,
            num_concurrent=args.concurrent,
            num_requests=args.requests,
            test_type=args.test,
        )
        print_results(results)


if __name__ == "__main__":
    asyncio.run(main())
