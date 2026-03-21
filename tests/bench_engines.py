#!/usr/bin/env python3
"""
Engine Speed + Accuracy Benchmark
==================================
Tests each batch-capable engine independently for:
  1. Batch latency (5 texts, warm)
  2. Accuracy on balanced AI/human snippets
  3. Best 1-engine and 2-engine combinations

Run: cd /root/sloptotal && source venv/bin/activate && python3 tests/bench_engines.py
"""

import sys
import os
import time
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch

# --- Test data: 10 human + 10 AI texts (short snippet-length, ~100-300 chars) ---

HUMAN_TEXTS = [
    "just got back from the dentist and my mouth is completely numb lol. tried to drink coffee and it went everywhere",
    "PSA if you're getting the SSL cert error after updating, clear your local cert cache. Took me 2 hours to figure that out smh.",
    "honestly the new season is kinda mid. they completely butchered the storyline and the pacing feels way off compared to the books",
    "My grandmother used to make this exact dish every Sunday. The secret ingredient is real saffron, not the powdered stuff from stores.",
    "Unpopular opinion but remote work has been terrible for junior developers. You miss out on so much osmotic learning just by sitting near senior engineers.",
    "i can't believe they're charging $18 for a sandwich now. like it's good but it's not THAT good. inflation is wild.",
    "anyone else's cat just randomly sprint around the house at 3am? mine sounds like a tiny horse galloping through the hallway",
    "the trick with sourdough is you gotta be patient with the starter. mine took like 2 weeks before it was really active enough to bake with",
    "ngl I mass applied to like 200 jobs and only heard back from 3. the job market rn is absolutely brutal especially for new grads",
    "went to that new ramen place on 5th. the broth was incredible but the noodles were kinda overcooked. still worth it tho, 7/10",
]

AI_TEXTS = [
    "Climate change is one of the most pressing issues facing humanity today. Rising global temperatures are causing widespread environmental disruption across ecosystems worldwide.",
    "Machine learning has revolutionized how we approach complex problems. By leveraging large datasets, these systems identify patterns that would be impossible for humans to detect manually.",
    "Effective communication is essential in any professional setting. Active listening, empathy, and adaptability are key components of successful interpersonal interactions.",
    "Quantum computing represents a paradigm shift in computational power, utilizing qubits in superposition states to achieve exponential speedup over classical systems.",
    "I'm thrilled to announce that after 3 years of dedicated research, our team has published groundbreaking findings on neural network optimization. This work demonstrates a 40% improvement in training efficiency.",
    "The Board of Directors reviewed quarterly financials noting revenue increased 12% year-over-year, driven by Asia-Pacific expansion. Operating margins improved to 18.3%, reflecting ongoing cost optimization.",
    "Here are five tips for improving your productivity that I've learned over 15 years in tech. First, prioritize ruthlessly using the Eisenhower Matrix. Second, eliminate distractions during deep work.",
    "The integration of artificial intelligence into healthcare has transformed diagnostic capabilities, enabling early detection of diseases through sophisticated pattern recognition algorithms.",
    "Sustainable development requires a balanced approach that considers economic growth, environmental protection, and social equity. Implementing green technologies is essential for long-term viability.",
    "Digital transformation has become a critical imperative for organizations seeking to maintain competitive advantage in today's rapidly evolving technological landscape.",
]

ALL_TEXTS = [t for pair in zip(HUMAN_TEXTS, AI_TEXTS) for t in pair]  # interleaved
ALL_LABELS = [0, 1] * 10  # 0=human, 1=AI


def load_engine(name):
    """Load an engine and return (engine_instance, load_time_ms)."""
    t0 = time.perf_counter()
    if name == "bert_raid":
        from app.engines.classifier_bert_raid import ClassifierBERTRaidEngine
        eng = ClassifierBERTRaidEngine()
        # Force model load
        eng.analyze("warmup text for loading")
    elif name == "e5":
        from app.engines.classifier_e5 import ClassifierE5Engine
        eng = ClassifierE5Engine()
        eng.analyze("warmup text for loading")
    elif name == "tmr":
        from app.engines.classifier_tmr import ClassifierTMREngine
        eng = ClassifierTMREngine()
        eng.analyze("warmup text for loading")
    elif name == "fakespot":
        from app.engines.classifier_fakespot import ClassifierFakespotEngine
        eng = ClassifierFakespotEngine()
        eng.analyze("warmup text for loading")
    else:
        raise ValueError(f"Unknown engine: {name}")
    load_ms = (time.perf_counter() - t0) * 1000
    return eng, load_ms


def bench_speed(eng, name, texts, runs=5):
    """Benchmark batch inference speed. Returns avg_ms."""
    # Warmup
    if hasattr(eng, 'analyze_batch'):
        eng.analyze_batch(texts[:2])
    else:
        for t in texts[:2]:
            eng.analyze(t)

    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        if hasattr(eng, 'analyze_batch'):
            eng.analyze_batch(texts)
        else:
            for t in texts:
                eng.analyze(t)
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)

    avg = statistics.mean(times)
    mn = min(times)
    mx = max(times)
    per = avg / len(texts)
    return avg, mn, mx, per


def bench_accuracy(eng, name):
    """Run all 20 texts and compute accuracy metrics."""
    scores = []
    if hasattr(eng, 'analyze_batch'):
        raw = eng.analyze_batch([t for t in HUMAN_TEXTS + AI_TEXTS])
        scores = list(raw)
    else:
        for t in HUMAN_TEXTS + AI_TEXTS:
            r = eng.analyze(t)
            scores.append(r.score)

    # First 10 are human (label=0), last 10 are AI (label=1)
    human_scores = scores[:10]
    ai_scores = scores[10:]

    # Metrics at threshold 0.5
    tp = sum(1 for s in ai_scores if s >= 0.5)
    fn = sum(1 for s in ai_scores if s < 0.5)
    fp = sum(1 for s in human_scores if s >= 0.5)
    tn = sum(1 for s in human_scores if s < 0.5)

    accuracy = (tp + tn) / 20
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # Average scores per class
    avg_human = statistics.mean(human_scores)
    avg_ai = statistics.mean(ai_scores)
    gap = avg_ai - avg_human  # discrimination gap (higher = better)

    return {
        "human_scores": human_scores,
        "ai_scores": ai_scores,
        "avg_human": avg_human,
        "avg_ai": avg_ai,
        "gap": gap,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
    }


def test_combination(engines, names, threshold=0.5):
    """Test a combination of engines with equal weighting."""
    n_engines = len(engines)
    all_scores = []

    for eng in engines:
        if hasattr(eng, 'analyze_batch'):
            raw = eng.analyze_batch(HUMAN_TEXTS + AI_TEXTS)
            all_scores.append(list(raw))
        else:
            scores = []
            for t in HUMAN_TEXTS + AI_TEXTS:
                r = eng.analyze(t)
                scores.append(r.score)
            all_scores.append(scores)

    # Average across engines
    combined = [statistics.mean(s[i] for s in all_scores) for i in range(20)]
    human_combined = combined[:10]
    ai_combined = combined[10:]

    tp = sum(1 for s in ai_combined if s >= threshold)
    fn = sum(1 for s in ai_combined if s < threshold)
    fp = sum(1 for s in human_combined if s >= threshold)
    tn = sum(1 for s in human_combined if s < threshold)

    accuracy = (tp + tn) / 20
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    avg_human = statistics.mean(human_combined)
    avg_ai = statistics.mean(ai_combined)
    gap = avg_ai - avg_human

    return {
        "accuracy": accuracy, "f1": f1, "gap": gap,
        "avg_human": avg_human, "avg_ai": avg_ai,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
    }


def main():
    ENGINE_NAMES = ["bert_raid", "e5", "tmr", "fakespot"]

    print("=" * 80)
    print("ENGINE SPEED + ACCURACY BENCHMARK")
    print("=" * 80)
    print(f"Test data: {len(HUMAN_TEXTS)} human + {len(AI_TEXTS)} AI texts")
    print(f"Batch size: 5 (snippet extension workload)")
    print()

    # --- Phase 1: Load and benchmark each engine ---
    engines = {}
    results = {}

    for name in ENGINE_NAMES:
        print(f"Loading {name}...")
        eng, load_ms = load_engine(name)
        engines[name] = eng
        print(f"  Loaded in {load_ms:.0f}ms")

        # Speed: batch of 5
        batch5 = (HUMAN_TEXTS[:3] + AI_TEXTS[:2])
        avg5, mn5, mx5, per5 = bench_speed(eng, name, batch5)

        # Speed: batch of 10
        batch10 = HUMAN_TEXTS[:5] + AI_TEXTS[:5]
        avg10, mn10, mx10, per10 = bench_speed(eng, name, batch10)

        # Accuracy
        acc = bench_accuracy(eng, name)

        results[name] = {
            "speed_5": {"avg": avg5, "min": mn5, "max": mx5, "per": per5},
            "speed_10": {"avg": avg10, "min": mn10, "max": mx10, "per": per10},
            "accuracy": acc,
        }

        print(f"  Speed (5 texts):  avg={avg5:.0f}ms  min={mn5:.0f}ms  max={mx5:.0f}ms  per_text={per5:.1f}ms")
        print(f"  Speed (10 texts): avg={avg10:.0f}ms  min={mn10:.0f}ms  max={mx10:.0f}ms  per_text={per10:.1f}ms")
        print(f"  Accuracy: {acc['accuracy']*100:.0f}% | F1={acc['f1']:.3f} | "
              f"gap={acc['gap']:.3f} (human={acc['avg_human']:.3f} ai={acc['avg_ai']:.3f})")
        print(f"  Confusion: TP={acc['tp']} FN={acc['fn']} FP={acc['fp']} TN={acc['tn']}")
        print()

    # --- Phase 2: Summary table ---
    print("=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Engine':<12} {'5-batch ms':>10} {'per-text':>10} {'Acc%':>6} {'F1':>6} {'Gap':>6} {'FP':>4} {'FN':>4}")
    print("-" * 70)
    for name in ENGINE_NAMES:
        r = results[name]
        s = r["speed_5"]
        a = r["accuracy"]
        print(f"{name:<12} {s['avg']:>10.0f} {s['per']:>10.1f} {a['accuracy']*100:>6.0f} {a['f1']:>6.3f} {a['gap']:>6.3f} {a['fp']:>4} {a['fn']:>4}")
    print()

    # --- Phase 3: Per-text score breakdown ---
    print("=" * 80)
    print("PER-TEXT SCORES (raw probabilities)")
    print("=" * 80)
    for i, text in enumerate(HUMAN_TEXTS):
        scores = " | ".join(f"{name}={results[name]['accuracy']['human_scores'][i]:.3f}" for name in ENGINE_NAMES)
        preview = text[:60].replace('\n', ' ')
        print(f"  HUMAN[{i}] {scores}  «{preview}...»")
    print()
    for i, text in enumerate(AI_TEXTS):
        scores = " | ".join(f"{name}={results[name]['accuracy']['ai_scores'][i]:.3f}" for name in ENGINE_NAMES)
        preview = text[:60].replace('\n', ' ')
        print(f"  AI[{i}]    {scores}  «{preview}...»")
    print()

    # --- Phase 4: Test all 2-engine combinations ---
    print("=" * 80)
    print("2-ENGINE COMBINATIONS (parallel execution, equal weight)")
    print("=" * 80)

    combos = []
    for i, n1 in enumerate(ENGINE_NAMES):
        for n2 in ENGINE_NAMES[i+1:]:
            # Speed: max of the two (they run in parallel)
            parallel_ms = max(results[n1]["speed_5"]["avg"], results[n2]["speed_5"]["avg"])
            combo_acc = test_combination([engines[n1], engines[n2]], [n1, n2])
            combos.append({
                "name": f"{n1}+{n2}",
                "parallel_ms": parallel_ms,
                "acc": combo_acc,
            })

    print(f"{'Combination':<22} {'Parallel ms':>12} {'Acc%':>6} {'F1':>6} {'Gap':>6} {'FP':>4} {'FN':>4}")
    print("-" * 70)
    for c in sorted(combos, key=lambda x: -x["acc"]["f1"]):
        a = c["acc"]
        print(f"{c['name']:<22} {c['parallel_ms']:>12.0f} {a['accuracy']*100:>6.0f} {a['f1']:>6.3f} {a['gap']:>6.3f} {a['fp']:>4} {a['fn']:>4}")
    print()

    # --- Phase 5: Test single-engine as snippet scanner ---
    print("=" * 80)
    print("SINGLE ENGINE AS SNIPPET SCANNER")
    print("=" * 80)
    for name in sorted(ENGINE_NAMES, key=lambda n: results[n]["speed_5"]["avg"]):
        r = results[name]
        s = r["speed_5"]
        a = r["accuracy"]
        print(f"  {name:<12}: {s['avg']:>6.0f}ms/5-batch | F1={a['f1']:.3f} | Acc={a['accuracy']*100:.0f}% | Gap={a['gap']:.3f}")
    print()

    # --- Phase 6: Recommendation ---
    print("=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)

    # Find fastest combo with F1 >= 0.7
    good_combos = [c for c in combos if c["acc"]["f1"] >= 0.7]
    if good_combos:
        best = min(good_combos, key=lambda x: x["parallel_ms"])
        print(f"  Best fast combo (F1>=0.7): {best['name']} — {best['parallel_ms']:.0f}ms, F1={best['acc']['f1']:.3f}")
    else:
        print("  No 2-engine combo reached F1>=0.7")

    # Find best F1 combo regardless of speed
    best_f1 = max(combos, key=lambda x: x["acc"]["f1"])
    print(f"  Best accuracy combo:       {best_f1['name']} — {best_f1['parallel_ms']:.0f}ms, F1={best_f1['acc']['f1']:.3f}")

    # Find fastest single engine with F1 >= 0.7
    good_singles = [(n, results[n]) for n in ENGINE_NAMES if results[n]["accuracy"]["f1"] >= 0.7]
    if good_singles:
        best_single = min(good_singles, key=lambda x: x[1]["speed_5"]["avg"])
        print(f"  Best single engine (F1>=0.7): {best_single[0]} — {best_single[1]['speed_5']['avg']:.0f}ms, F1={best_single[1]['accuracy']['f1']:.3f}")

    # Current setup comparison
    current_ms = max(results["bert_raid"]["speed_5"]["avg"], results["fakespot"]["speed_5"]["avg"])
    current_acc = test_combination([engines["bert_raid"], engines["fakespot"]], ["bert_raid", "fakespot"])
    print(f"\n  Current (bert_raid+fakespot): {current_ms:.0f}ms, F1={current_acc['f1']:.3f}, Gap={current_acc['gap']:.3f}")
    print()


if __name__ == "__main__":
    main()
