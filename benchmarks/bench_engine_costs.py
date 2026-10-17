#!/usr/bin/env python3
"""What each engine costs: resident memory after loading, and median latency.

Every engine is measured in its own fresh process, so one engine's model never
inflates another's memory. For each of the 23 engines it records:

  * memory: peak resident set size after the model is loaded and has run once, minus
    the same process before the load (torch, transformers and the app already
    imported), in MB;
  * latency: the median time of `analyze()` on a text of about 300 words, over
    RUNS different texts, on CPU, with the thread count the app uses.

The texts differ on purpose. Eight engines share one GPT-2 forward pass through
`app/engines/gpt2_cache.py` (two of them also a DistilGPT-2 one), which is cached
by text, so repeating one text would time a cache hit. For those engines the
table also gives the marginal latency once the shared pass is cached, which is
what they cost in a real report.

Run (from the repository root):

    python benchmarks/bench_engine_costs.py > engine-costs.md
    python benchmarks/bench_engine_costs.py --threads 4 --runs 5
    python benchmarks/bench_engine_costs.py --engine classifier_tmr   # one engine, JSON

The first run downloads every model (about 9 GB); run it once beforehand if the
download should not be part of a measurement. Needs numpy, torch, transformers
and psutil, all in requirements.txt.
"""

import argparse
import glob
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from itertools import zip_longest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORDS = 300
RUNS = 12
# Engines that read the shared GPT-2 forward pass (binoculars and cross_perplexity
# also read DistilGPT-2's).
SHARED_GPT2 = {
    "binoculars",
    "fast_detectgpt",
    "perplexity",
    "cross_perplexity",
    "gltr",
    "log_rank",
    "diveye",
    "burstiness",
}


def texts(n: int) -> list[str]:
    """n different human texts of WORDS words from the SlopBench corpus, interleaved across its sources."""
    per_source = []
    for path in sorted(
        glob.glob(os.path.join(ROOT, "tests/eval/slopbench/corpus/human-*.jsonl"))
    ):
        found = []
        for line in open(path, encoding="utf-8"):
            words = json.loads(line)["text"].split()
            if len(words) >= WORDS:
                found.append(" ".join(words[:WORDS]))
                if len(found) == n:
                    break
        if found:
            per_source.append(found)
    out = [t for round_ in zip_longest(*per_source) for t in round_ if t is not None]
    if len(out) < n:
        raise SystemExit(f"need {n} corpus texts of {WORDS} words, found {len(out)}")
    return out[:n]


def rss_mb() -> float:
    """Peak resident set size of this process so far, in MB. The peak, not the current value: under memory pressure
    the OS pages model weights out and the current RSS drops, which would understate what the engine needs."""
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return (
        peak / 1e6 if sys.platform == "darwin" else peak / 1e3
    )  # bytes on macOS, kilobytes on Linux


def measure(name: str, threads: int, runs: int) -> dict:
    import torch

    torch.set_num_threads(threads)
    from app import analyzer

    engine = dict(analyzer._engines)[name]
    sample = texts(runs + 1)
    before = rss_mb()
    t0 = time.perf_counter()
    engine.analyze(sample[0])  # first call loads the model
    load_s = time.perf_counter() - t0
    after = rss_mb()

    cold = []
    for text in sample[1:]:  # unseen texts: nothing cached
        t = time.perf_counter()
        engine.analyze(text)
        cold.append(time.perf_counter() - t)

    result = {
        "engine": name,
        "memory_mb": round(after - before),
        "load_s": round(load_s, 1),
        "median_s": round(statistics.median(cold), 3),
    }
    if name in SHARED_GPT2:
        # The shared cache keeps only a few texts, so time the second call on a text right after the first.
        warm = []
        for text in sample[1:]:
            engine.analyze(text)  # fills the shared pass for this text
            t = time.perf_counter()
            engine.analyze(text)  # served from it
            warm.append(time.perf_counter() - t)
        result["marginal_s"] = round(statistics.median(warm), 3)
    return result


def machine() -> str:
    import psutil

    cpu = platform.processor() or platform.machine()
    if sys.platform == "darwin":
        cpu = (
            subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            or cpu
        )
    elif os.path.exists("/proc/cpuinfo"):
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    ram = psutil.virtual_memory().total / 1024**3
    return f"{cpu}, {os.cpu_count()} cores, {ram:.0f} GB RAM, {platform.system()} {platform.release()}"


def run_all(threads: int, runs: int) -> None:
    from app import analyzer

    names = [name for name, _ in analyzer._engines]
    texts(runs + 1)  # fail now, not once per engine
    rows = []
    for name in names:
        print(f"measuring {name} ...", file=sys.stderr, flush=True)
        out = subprocess.run(
            [
                sys.executable,
                __file__,
                "--engine",
                name,
                "--threads",
                str(threads),
                "--runs",
                str(runs),
            ],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "CUDA_VISIBLE_DEVICES": "",
                "TOKENIZERS_PARALLELISM": "false",
            },
        )
        lines = [line for line in out.stdout.splitlines() if line.startswith("{")]
        if out.returncode or not lines:
            print(f"{name} failed:\n{out.stderr[-2000:]}", file=sys.stderr)
            rows.append({"engine": name, "error": True})
            continue
        rows.append(json.loads(lines[-1]))

    import torch

    import psutil

    print(f"Measured on: {machine()}.")
    print(
        f"At the start: {os.getloadavg()[0]:.1f} load average, {psutil.swap_memory().used / 1e9:.1f} GB of swap in use."
    )
    print(
        f"Python {platform.python_version()}, torch {torch.__version__}, CPU, {threads} thread(s) per engine, "
    )
    print(f"median of {runs} different texts of {WORDS} words each.\n")
    print(
        "| Engine | Peak memory after load (MB) | Median latency (s) | Marginal latency, shared pass cached (s) |"
    )
    print("|---|---:|---:|---:|")
    for r in rows:
        if r.get("error"):
            print(f"| {r['engine']} | failed | failed | |")
            continue
        marginal = f"{r['marginal_s']:.3f}" if "marginal_s" in r else ""
        print(
            f"| {r['engine']} | {r['memory_mb']} | {r['median_s']:.3f} | {marginal} |"
        )
    json.dump(rows, sys.stderr)
    print(file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--engine", help="measure one engine and print one JSON line")
    ap.add_argument(
        "--threads", type=int, default=int(os.getenv("SLOPTOTAL_TORCH_THREADS", "1"))
    )
    ap.add_argument("--runs", type=int, default=RUNS)
    args = ap.parse_args()
    if args.engine:
        print(json.dumps(measure(args.engine, args.threads, args.runs)))
    else:
        run_all(args.threads, args.runs)


if __name__ == "__main__":
    main()
