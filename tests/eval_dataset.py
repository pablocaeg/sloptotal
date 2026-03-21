#!/usr/bin/env python3
"""
SlopTotal Accuracy Evaluation on RAID Dataset
==============================================
Samples balanced human/AI texts from the RAID dataset,
runs them through the API, and computes per-engine and
overall accuracy metrics (precision, recall, F1, calibration).
"""

import asyncio
import random
import time
import json
import sys
import httpx
import numpy as np
from collections import defaultdict
from datasets import load_dataset

API_URL = "http://localhost:8000"
SAMPLE_SIZE = 200  # per class (200 human + 200 AI = 400 total)
BATCH_SIZE = 10    # snippets per API call
CONCURRENCY = 2    # parallel API calls
SEED = 42
# Target AI models to sample from (ensures model diversity)
TARGET_MODELS = {"llama-chat", "mpt", "mpt-chat", "gpt2", "mistral", "mistral-chat"}
PER_MODEL_TARGET = 40  # ~200 AI total spread across models

random.seed(SEED)
np.random.seed(SEED)


def load_samples():
    """Load balanced, diverse samples from RAID dataset."""
    print(f"Loading RAID dataset (streaming, multi-model)...")
    ds = load_dataset("liamdugan/raid", split="train", streaming=True)

    human_texts = []
    ai_by_model = defaultdict(list)

    seen = 0
    models_full = set()
    for row in ds:
        text = row["generation"]
        model = row["model"]
        domain = row["domain"]

        if len(text) < 50:
            continue

        text = text[:2000]

        if model == "human":
            if len(human_texts) < SAMPLE_SIZE * 3:
                human_texts.append({"text": text, "label": 0, "domain": domain, "model": "human"})
        elif model in TARGET_MODELS:
            if len(ai_by_model[model]) < PER_MODEL_TARGET * 3:
                ai_by_model[model].append({"text": text, "label": 1, "domain": domain, "model": model})
            else:
                models_full.add(model)

        seen += 1
        # Stop once we have enough of everything
        human_ok = len(human_texts) >= SAMPLE_SIZE * 3
        ai_ok = all(len(ai_by_model[m]) >= PER_MODEL_TARGET * 3 for m in TARGET_MODELS)
        if human_ok and ai_ok:
            break
        if seen % 10000 == 0:
            model_counts = {m: len(v) for m, v in ai_by_model.items()}
            print(f"  Scanned {seen}: {len(human_texts)} human, AI: {model_counts}")

    print(f"  Total scanned: {seen} rows")
    print(f"  Human pool: {len(human_texts)}")
    for m in sorted(ai_by_model.keys()):
        print(f"  {m} pool: {len(ai_by_model[m])}")

    # Sample balanced across models
    human_sample = random.sample(human_texts, min(SAMPLE_SIZE, len(human_texts)))

    ai_sample = []
    for model in sorted(ai_by_model.keys()):
        pool = ai_by_model[model]
        n = min(PER_MODEL_TARGET, len(pool))
        ai_sample.extend(random.sample(pool, n))

    # If we need more AI samples, top up from the largest pools
    while len(ai_sample) < SAMPLE_SIZE:
        for model in sorted(ai_by_model.keys()):
            remaining = [t for t in ai_by_model[model] if t not in ai_sample]
            if remaining:
                ai_sample.append(random.choice(remaining))
                if len(ai_sample) >= SAMPLE_SIZE:
                    break

    samples = human_sample + ai_sample
    random.shuffle(samples)

    print(f"  Final sample: {len(human_sample)} human + {len(ai_sample)} AI = {len(samples)} total")

    # Distribution
    model_dist = defaultdict(int)
    domain_dist = defaultdict(int)
    for s in samples:
        model_dist[s["model"]] += 1
        domain_dist[s["domain"]] += 1
    print(f"  Models: {dict(model_dist)}")
    print(f"  Domains: {dict(domain_dist)}")

    return samples


async def run_quick_score(client: httpx.AsyncClient, text: str) -> dict:
    """Call /api/quick-score for a single text."""
    try:
        resp = await client.post(
            f"{API_URL}/api/quick-score",
            json={"text": text},
            timeout=30.0,
        )
        if resp.status_code == 429:
            await asyncio.sleep(2)
            resp = await client.post(
                f"{API_URL}/api/quick-score",
                json={"text": text},
                timeout=30.0,
            )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e), "score": 50.0, "verdict": "error", "engines": []}


async def run_snippet_batch(client: httpx.AsyncClient, snippets: list[dict]) -> dict:
    """Call /api/scan/snippets for a batch."""
    try:
        payload = {
            "snippets": [
                {"id": str(i), "text": s["text"]}
                for i, s in enumerate(snippets)
            ]
        }
        resp = await client.post(
            f"{API_URL}/api/scan/snippets",
            json=payload,
            timeout=60.0,
        )
        if resp.status_code == 429:
            await asyncio.sleep(2)
            resp = await client.post(
                f"{API_URL}/api/scan/snippets",
                json=payload,
                timeout=60.0,
            )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e), "results": []}


async def evaluate_quick_score(samples: list[dict]) -> list[dict]:
    """Run all samples through /api/quick-score."""
    print(f"\n{'='*60}")
    print(f"EVALUATING: /api/quick-score (4 engines)")
    print(f"{'='*60}")

    results = []
    semaphore = asyncio.Semaphore(CONCURRENCY)
    completed = 0
    start = time.perf_counter()

    async def process_one(sample):
        nonlocal completed
        async with semaphore:
            resp = await run_quick_score(client, sample["text"])
            completed += 1
            if completed % 50 == 0:
                elapsed = time.perf_counter() - start
                rate = completed / elapsed
                eta = (len(samples) - completed) / rate
                print(f"  Progress: {completed}/{len(samples)} ({rate:.1f}/s, ETA {eta:.0f}s)")
            return {**sample, "response": resp}

    async with httpx.AsyncClient() as client:
        tasks = [process_one(s) for s in samples]
        results = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - start
    print(f"  Completed {len(results)} in {elapsed:.1f}s ({len(results)/elapsed:.1f} req/s)")

    return results


async def evaluate_snippets(samples: list[dict]) -> list[dict]:
    """Run all samples through /api/scan/snippets in batches."""
    print(f"\n{'='*60}")
    print(f"EVALUATING: /api/scan/snippets (3 engines, batched)")
    print(f"{'='*60}")

    results = []
    semaphore = asyncio.Semaphore(CONCURRENCY)
    start = time.perf_counter()

    # Split into batches
    batches = []
    for i in range(0, len(samples), BATCH_SIZE):
        batches.append(samples[i:i + BATCH_SIZE])

    completed_batches = 0

    async def process_batch(batch):
        nonlocal completed_batches
        async with semaphore:
            resp = await run_snippet_batch(client, batch)
            completed_batches += 1
            if completed_batches % 5 == 0:
                elapsed = time.perf_counter() - start
                done_samples = completed_batches * BATCH_SIZE
                rate = done_samples / elapsed
                remaining = len(samples) - done_samples
                eta = remaining / rate if rate > 0 else 0
                print(f"  Progress: {done_samples}/{len(samples)} ({rate:.1f}/s, ETA {eta:.0f}s)")
            return batch, resp

    async with httpx.AsyncClient() as client:
        tasks = [process_batch(b) for b in batches]
        batch_results = await asyncio.gather(*tasks)

    # Merge batch results back with labels
    for batch, resp in batch_results:
        resp_results = resp.get("results", [])
        for i, sample in enumerate(batch):
            if i < len(resp_results):
                results.append({**sample, "response": resp_results[i]})
            else:
                results.append({**sample, "response": {"score": 50.0, "indicator": "?", "error": "missing"}})

    elapsed = time.perf_counter() - start
    print(f"  Completed {len(results)} in {elapsed:.1f}s")

    return results


def compute_metrics(results: list[dict], endpoint: str):
    """Compute accuracy metrics from results."""
    print(f"\n{'='*60}")
    print(f"RESULTS: {endpoint}")
    print(f"{'='*60}")

    # Extract scores and labels
    scores = []
    labels = []
    engine_scores = defaultdict(list)  # engine_name -> list of (score, label)

    for r in results:
        resp = r["response"]
        label = r["label"]

        if "error" in resp and resp.get("verdict") == "error":
            continue

        # Overall score
        score = resp.get("score", 50.0)
        scores.append(score / 100.0)  # Normalize to 0-1
        labels.append(label)

        # Per-engine scores
        engines = resp.get("engines", [])
        for eng in engines:
            eng_name = eng.get("engine", eng.get("name", "unknown"))
            eng_score = eng.get("score", 50.0) / 100.0
            engine_scores[eng_name].append((eng_score, label))

    scores = np.array(scores)
    labels = np.array(labels)

    if len(scores) == 0:
        print("  No valid results!")
        return {}

    print(f"\n  Valid samples: {len(scores)} ({sum(labels)} AI, {len(labels) - sum(labels)} human)")

    # --- Per-Engine Analysis ---
    print(f"\n  {'Engine':<25} {'Acc':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'AvgH':>6} {'AvgA':>6}")
    print(f"  {'-'*25} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")

    engine_metrics = {}
    for eng_name in sorted(engine_scores.keys()):
        eng_data = engine_scores[eng_name]
        eng_s = np.array([s for s, _ in eng_data])
        eng_l = np.array([l for _, l in eng_data])

        # At 0.5 threshold
        eng_pred = (eng_s > 0.5).astype(int)
        tp = ((eng_pred == 1) & (eng_l == 1)).sum()
        fp = ((eng_pred == 1) & (eng_l == 0)).sum()
        fn = ((eng_pred == 0) & (eng_l == 1)).sum()
        tn = ((eng_pred == 0) & (eng_l == 0)).sum()

        acc = (tp + tn) / len(eng_l) if len(eng_l) > 0 else 0
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

        avg_human = eng_s[eng_l == 0].mean() if (eng_l == 0).any() else 0
        avg_ai = eng_s[eng_l == 1].mean() if (eng_l == 1).any() else 0

        print(f"  {eng_name:<25} {acc:>5.1%} {prec:>5.1%} {rec:>5.1%} {f1:>5.1%} {avg_human:>5.1%} {avg_ai:>5.1%}")

        engine_metrics[eng_name] = {
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "avg_human_score": round(avg_human, 4),
            "avg_ai_score": round(avg_ai, 4),
            "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        }

    # --- Overall Combined Score ---
    print(f"\n  --- Overall Combined Score ---")

    thresholds = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    best_f1 = 0
    best_thresh = 0.5

    print(f"\n  {'Thresh':>7} {'Acc':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'FPR':>6}")
    print(f"  {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")

    for t in thresholds:
        pred = (scores > t).astype(int)
        tp = ((pred == 1) & (labels == 1)).sum()
        fp = ((pred == 1) & (labels == 0)).sum()
        fn = ((pred == 0) & (labels == 1)).sum()
        tn = ((pred == 0) & (labels == 0)).sum()

        acc = (tp + tn) / len(labels)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

        marker = ""
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = t
            marker = " <-- best F1"

        print(f"  {t:>6.0%}  {acc:>5.1%} {prec:>5.1%} {rec:>5.1%} {f1:>5.1%} {fpr:>5.1%}{marker}")

    print(f"\n  Best threshold: {best_thresh:.0%} (F1={best_f1:.1%})")

    # --- Calibration Analysis ---
    print(f"\n  --- Calibration Analysis ---")
    print(f"  (When we say X%, how often is it actually AI?)")
    print(f"\n  {'Bucket':>12} {'Count':>6} {'Actual AI%':>10} {'Gap':>6}")
    print(f"  {'-'*12} {'-'*6} {'-'*10} {'-'*6}")

    buckets = [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    for lo, hi in buckets:
        mask = (scores >= lo) & (scores < hi)
        if mask.sum() == 0:
            continue
        bucket_labels = labels[mask]
        actual_ai = bucket_labels.mean()
        predicted_midpoint = (lo + hi) / 2
        gap = actual_ai - predicted_midpoint
        print(f"  {lo:.0%}-{hi:.0%}     {mask.sum():>5}  {actual_ai:>9.1%}  {gap:>+5.1%}")

    # --- Per-Model Breakdown ---
    model_results = defaultdict(list)
    for r in results:
        resp = r["response"]
        if "error" in resp and resp.get("verdict") == "error":
            continue
        score = resp.get("score", 50.0) / 100.0
        model_results[r["model"]].append((score, r["label"]))

    if len(model_results) > 1:
        print(f"\n  --- Per AI Model Detection Rate (at {best_thresh:.0%} threshold) ---")
        print(f"\n  {'Model':<25} {'Count':>6} {'Detected':>8} {'AvgScore':>9}")
        print(f"  {'-'*25} {'-'*6} {'-'*8} {'-'*9}")

        for model_name in sorted(model_results.keys()):
            data = model_results[model_name]
            m_scores = np.array([s for s, _ in data])
            m_labels = np.array([l for _, l in data])
            detected = (m_scores > best_thresh).mean()
            avg = m_scores.mean()
            print(f"  {model_name:<25} {len(data):>5}  {detected:>7.1%}  {avg:>8.1%}")

    # --- Per-Domain Breakdown ---
    domain_results = defaultdict(list)
    for r in results:
        resp = r["response"]
        if "error" in resp and resp.get("verdict") == "error":
            continue
        score = resp.get("score", 50.0) / 100.0
        domain_results[r["domain"]].append((score, r["label"]))

    if len(domain_results) > 1:
        print(f"\n  --- Per Domain Performance (at {best_thresh:.0%} threshold) ---")
        print(f"\n  {'Domain':<20} {'Count':>6} {'Acc':>6} {'FPR':>6} {'TPR':>6}")
        print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")

        for domain in sorted(domain_results.keys()):
            data = domain_results[domain]
            d_scores = np.array([s for s, _ in data])
            d_labels = np.array([l for _, l in data])
            d_pred = (d_scores > best_thresh).astype(int)
            tp = ((d_pred == 1) & (d_labels == 1)).sum()
            fp = ((d_pred == 1) & (d_labels == 0)).sum()
            fn = ((d_pred == 0) & (d_labels == 1)).sum()
            tn = ((d_pred == 0) & (d_labels == 0)).sum()
            acc = (tp + tn) / len(d_labels) if len(d_labels) > 0 else 0
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
            tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
            print(f"  {domain:<20} {len(data):>5}  {acc:>5.1%} {fpr:>5.1%} {tpr:>5.1%}")

    return {
        "endpoint": endpoint,
        "n_samples": len(scores),
        "best_threshold": best_thresh,
        "best_f1": round(best_f1, 4),
        "engine_metrics": engine_metrics,
    }


async def main():
    # Check server
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{API_URL}/health", timeout=5.0)
            health = resp.json()
            print(f"Server: {health['status']} ({health['engines']} engines)")
        except Exception as e:
            print(f"Server not reachable: {e}")
            sys.exit(1)

    # Load dataset
    samples = load_samples()

    # Run evaluations
    quick_results = await evaluate_quick_score(samples)
    quick_metrics = compute_metrics(quick_results, "/api/quick-score")

    snippet_results = await evaluate_snippets(samples)
    snippet_metrics = compute_metrics(snippet_results, "/api/scan/snippets")

    # Save raw results for further analysis
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sample_size": SAMPLE_SIZE,
        "quick_score_metrics": quick_metrics,
        "snippet_metrics": snippet_metrics,
    }
    with open("tests/eval_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nRaw results saved to tests/eval_results.json")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  quick-score  best F1: {quick_metrics.get('best_f1', 0):.1%} at threshold {quick_metrics.get('best_threshold', 0.5):.0%}")
    print(f"  snippets     best F1: {snippet_metrics.get('best_f1', 0):.1%} at threshold {snippet_metrics.get('best_threshold', 0.5):.0%}")


if __name__ == "__main__":
    asyncio.run(main())
