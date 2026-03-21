#!/usr/bin/env python3
"""
Diagnostic: dump per-sample engine scores from MAGE to find better calibration.
Outputs CSV of raw engine scores + labels for analysis.
"""
import asyncio
import random
import json
import sys
import time
from collections import defaultdict

import httpx
import numpy as np
from datasets import load_dataset

API_URL = "http://localhost:8000"
SEED = 42
random.seed(SEED)
np.random.seed(SEED)


def load_mage_samples(n_per_class=100):
    print("Loading MAGE dataset...")
    ds = load_dataset("yaful/MAGE", split="train", streaming=True, trust_remote_code=True)
    human, ai = [], []
    for row in ds:
        text = row.get("text", "")
        label = row.get("label", -1)
        domain = row.get("domain", "unknown")
        if len(text) < 60:
            continue
        text = text[:2000]
        if label == 0 and len(human) < n_per_class * 3:
            human.append({"text": text, "label": 0, "domain": domain})
        elif label == 1 and len(ai) < n_per_class * 3:
            ai.append({"text": text, "label": 1, "domain": domain})
        if len(human) >= n_per_class * 3 and len(ai) >= n_per_class * 3:
            break
    h = random.sample(human, min(n_per_class, len(human)))
    a = random.sample(ai, min(n_per_class, len(ai)))
    print(f"  Selected: {len(h)} human + {len(a)} AI")
    return h + a


async def get_quick_scores(client, text):
    """Get per-engine scores from quick-score endpoint."""
    try:
        r = await client.post(f"{API_URL}/api/quick-score", json={"text": text}, timeout=30.0)
        if r.status_code == 429:
            await asyncio.sleep(2)
            r = await client.post(f"{API_URL}/api/quick-score", json={"text": text}, timeout=30.0)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  Error: {e}")
    return None


async def main():
    # Health check
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_URL}/health", timeout=5.0)
        print(f"Server: {r.json()['status']} ({r.json()['engines']} engines)")

    samples = load_mage_samples(100)
    random.shuffle(samples)

    results = []
    sem = asyncio.Semaphore(2)

    async def process(sample, idx):
        async with sem:
            resp = await get_quick_scores(client, sample["text"])
            if idx % 25 == 0:
                print(f"  [{idx}/{len(samples)}]")
            if resp:
                engines = {e["engine"]: e["score"] for e in resp.get("engines", [])}
                return {
                    "label": sample["label"],
                    "domain": sample["domain"],
                    "overall_score": resp["score"],
                    "verdict": resp["verdict"],
                    "confidence": resp["confidence"],
                    **engines,
                }
            return None

    async with httpx.AsyncClient() as client:
        tasks = [process(s, i) for i, s in enumerate(samples)]
        raw = await asyncio.gather(*tasks)

    results = [r for r in raw if r]
    print(f"\nGot {len(results)} results")

    # Convert to arrays for analysis
    labels = np.array([r["label"] for r in results])
    scores = np.array([r["overall_score"] for r in results])

    # Per-engine arrays
    engine_names = ["classifier_fakespot", "classifier_bert_raid", "classifier_e5",
                    "classifier_tmr", "linguistic", "formulaic"]
    engine_arrays = {}
    for eng in engine_names:
        engine_arrays[eng] = np.array([r.get(eng, 50.0) for r in results])

    human_mask = labels == 0
    ai_mask = labels == 1

    print(f"\n{'='*70}")
    print(f"PER-ENGINE SCORE DISTRIBUTIONS (MAGE)")
    print(f"{'='*70}")
    print(f"{'Engine':<25} {'Human':>10} {'AI':>10} {'Gap':>8} {'Human<50%':>10} {'AI>50%':>10}")
    print(f"{'-'*25} {'-'*10} {'-'*10} {'-'*8} {'-'*10} {'-'*10}")
    for eng in engine_names:
        h = engine_arrays[eng][human_mask]
        a = engine_arrays[eng][ai_mask]
        h_mean = h.mean()
        a_mean = a.mean()
        gap = a_mean - h_mean
        h_below_50 = (h < 50).sum() / len(h) * 100
        a_above_50 = (a > 50).sum() / len(a) * 100
        print(f"{eng:<25} {h_mean:>9.1f}% {a_mean:>9.1f}% {gap:>+7.1f}% {h_below_50:>9.0f}% {a_above_50:>9.0f}%")

    # Fakespot deep dive - it's our best discriminator
    print(f"\n{'='*70}")
    print(f"FAKESPOT SCORE DISTRIBUTION (BEST DISCRIMINATOR)")
    print(f"{'='*70}")
    fs = engine_arrays["classifier_fakespot"]
    for lo, hi in [(0, 20), (20, 35), (35, 50), (50, 65), (65, 80), (80, 100.1)]:
        mask = (fs >= lo) & (fs < hi)
        h_in = (mask & human_mask).sum()
        a_in = (mask & ai_mask).sum()
        total = mask.sum()
        ai_pct = a_in / total * 100 if total > 0 else 0
        print(f"  Fakespot [{lo:>3}-{hi:>5.0f}): {total:>4} samples ({h_in:>3} human, {a_in:>3} AI) — {ai_pct:.0f}% are AI")

    # Misclassification analysis at threshold=40%
    threshold = 40.0
    print(f"\n{'='*70}")
    print(f"MISCLASSIFICATION ANALYSIS (threshold={threshold}%)")
    print(f"{'='*70}")

    # False positives: human scored > threshold
    fp_mask = human_mask & (scores > threshold)
    fp_count = fp_mask.sum()
    print(f"\nFalse positives (human scored >{threshold}%): {fp_count}/{human_mask.sum()}")
    if fp_count > 0:
        fp_results = [r for r, m in zip(results, fp_mask) if m]
        fp_results.sort(key=lambda r: r["overall_score"], reverse=True)
        for r in fp_results[:10]:
            print(f"  score={r['overall_score']:5.1f} fs={r.get('classifier_fakespot',0):5.1f} "
                  f"bert={r.get('classifier_bert_raid',0):5.1f} e5={r.get('classifier_e5',0):5.1f} "
                  f"tmr={r.get('classifier_tmr',0):5.1f} ling={r.get('linguistic',0):5.1f} "
                  f"form={r.get('formulaic',0):5.1f} domain={r['domain']}")

    # False negatives: AI scored <= threshold
    fn_mask = ai_mask & (scores <= threshold)
    fn_count = fn_mask.sum()
    print(f"\nFalse negatives (AI scored <={threshold}%): {fn_count}/{ai_mask.sum()}")
    if fn_count > 0:
        fn_results = [r for r, m in zip(results, fn_mask) if m]
        fn_results.sort(key=lambda r: r["overall_score"])
        for r in fn_results[:10]:
            print(f"  score={r['overall_score']:5.1f} fs={r.get('classifier_fakespot',0):5.1f} "
                  f"bert={r.get('classifier_bert_raid',0):5.1f} e5={r.get('classifier_e5',0):5.1f} "
                  f"tmr={r.get('classifier_tmr',0):5.1f} ling={r.get('linguistic',0):5.1f} "
                  f"form={r.get('formulaic',0):5.1f} domain={r['domain']}")

    # Optimal Fakespot-only threshold
    print(f"\n{'='*70}")
    print(f"FAKESPOT-ONLY F1 (if we used only Fakespot)")
    print(f"{'='*70}")
    fs_scores = engine_arrays["classifier_fakespot"] / 100.0
    best_f1 = 0
    best_t = 0
    for t in np.arange(0.30, 0.75, 0.05):
        pred = (fs_scores > t).astype(int)
        tp = ((pred == 1) & (labels == 1)).sum()
        fp = ((pred == 1) & (labels == 0)).sum()
        fn = ((pred == 0) & (labels == 1)).sum()
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        marker = " *" if f1 > best_f1 else ""
        if f1 > best_f1:
            best_f1 = f1
            best_t = t
        print(f"  thresh={t:.2f} prec={prec:.3f} rec={rec:.3f} F1={f1:.3f}{marker}")
    print(f"  Best Fakespot-only F1: {best_f1:.3f} at {best_t:.2f}")

    # Try simple combination: score = fakespot * w + (others_avg) * (1-w)
    print(f"\n{'='*70}")
    print(f"OPTIMAL FAKESPOT WEIGHT SEARCH")
    print(f"{'='*70}")
    others = (engine_arrays["classifier_bert_raid"] + engine_arrays["classifier_e5"] + engine_arrays["classifier_tmr"]) / 3 / 100.0
    fs_norm = engine_arrays["classifier_fakespot"] / 100.0

    best_combo_f1 = 0
    best_w = 0
    best_combo_t = 0
    for w in np.arange(0.3, 1.01, 0.05):
        combo = fs_norm * w + others * (1 - w)
        for t in np.arange(0.30, 0.70, 0.02):
            pred = (combo > t).astype(int)
            tp = ((pred == 1) & (labels == 1)).sum()
            fp = ((pred == 1) & (labels == 0)).sum()
            fn = ((pred == 0) & (labels == 1)).sum()
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
            if f1 > best_combo_f1:
                best_combo_f1 = f1
                best_w = w
                best_combo_t = t
    print(f"  Best combo: F1={best_combo_f1:.3f} at w={best_w:.2f}, thresh={best_combo_t:.2f}")

    # Try: Fakespot + linguistic/formulaic boost
    print(f"\n{'='*70}")
    print(f"FAKESPOT + HEURISTIC BOOST")
    print(f"{'='*70}")
    ling = engine_arrays["linguistic"] / 100.0
    form = engine_arrays["formulaic"] / 100.0
    heuristic = np.maximum(ling, form)

    best_boost_f1 = 0
    for w in [0.6, 0.7, 0.8, 0.9, 1.0]:
        for boost in [0.05, 0.10, 0.15, 0.20]:
            combo = fs_norm * w + others * (1 - w) + heuristic * boost
            for t in np.arange(0.30, 0.70, 0.02):
                pred = (combo > t).astype(int)
                tp = ((pred == 1) & (labels == 1)).sum()
                fp = ((pred == 1) & (labels == 0)).sum()
                fn = ((pred == 0) & (labels == 1)).sum()
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0
                f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
                if f1 > best_boost_f1:
                    best_boost_f1 = f1
                    print(f"  NEW BEST: F1={f1:.3f} w={w:.2f} boost={boost:.2f} thresh={t:.2f}")

    # Try: nonlinear Fakespot transform (sigmoid stretch around 0.5)
    print(f"\n{'='*70}")
    print(f"NONLINEAR FAKESPOT TRANSFORM")
    print(f"{'='*70}")
    best_nl_f1 = 0
    for steepness in [2, 4, 6, 8, 10]:
        # Sigmoid centered at 0.5: stretches scores away from 0.5
        fs_transformed = 1 / (1 + np.exp(-steepness * (fs_norm - 0.5)))
        for w in [0.6, 0.7, 0.8, 0.9]:
            combo = fs_transformed * w + others * (1 - w)
            for t in np.arange(0.30, 0.70, 0.02):
                pred = (combo > t).astype(int)
                tp = ((pred == 1) & (labels == 1)).sum()
                fp = ((pred == 1) & (labels == 0)).sum()
                fn = ((pred == 0) & (labels == 1)).sum()
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0
                f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
                if f1 > best_nl_f1:
                    best_nl_f1 = f1
                    print(f"  NEW BEST: F1={f1:.3f} steep={steepness} w={w:.2f} thresh={t:.2f}")

    # Dump raw data for further analysis
    with open("tests/mage_diagnostic.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw per-sample data saved to tests/mage_diagnostic.json")


if __name__ == "__main__":
    asyncio.run(main())
