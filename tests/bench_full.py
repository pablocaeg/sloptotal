#!/usr/bin/env python3
"""
Comprehensive Engine Benchmark for Snippet Scoring
====================================================
Tests every engine combination, weighting strategy, text-length behavior,
and scoring threshold to find the mathematically optimal configuration.

Run: cd /root/sloptotal && source venv/bin/activate && python3 tests/bench_full.py
"""

import sys
import os
import time
import statistics
import itertools
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Test data: 10 human + 10 AI texts ---

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

# Extra texts for robustness (longer, more diverse)
HUMAN_TEXTS_LONG = [
    "So I tried building my own PC for the first time and it was way harder than those YouTube videos make it look. Spent like 3 hours just trying to get the CPU cooler mounted properly. The thermal paste application was terrifying. But it actually posted on the first try which felt amazing. Now I just need to figure out why the RGB isn't working on two of the fans.",
    "My dog ate an entire loaf of bread off the counter while I was in the shower. He looked so proud of himself too, just sitting there with crumbs all over his face. Took him to the vet just in case and they said he'd be fine but might have an upset stomach. $200 vet bill for a $4 loaf of bread.",
    "Been a barista for 6 years and I can tell you that oat milk is by far the hardest to steam properly. It separates if you get it too hot and the foam never holds. Almond milk is easier but honestly most people can't tell the difference between a good and bad pour with alt milks. Just don't order a bone dry cappuccino with oat milk, please.",
    "Moving to a new city at 30 hits different than at 22. Back then you just showed up and made friends at every party. Now everyone has established friend groups and nobody wants to hang on a Tuesday because they have partners and kids and actual responsibilities. Been here 4 months and my social circle is basically my coworkers and one guy from my gym.",
    "I've been doing pottery for about a year now and the thing nobody tells you is how much time you spend just wedging clay. Like 80% of pottery is not the fun wheel part. It's prep, and trimming, and waiting for things to dry, and glazing, and more waiting. But when something comes out of the kiln and it's actually good? Best feeling.",
]

AI_TEXTS_LONG = [
    "The rapid advancement of renewable energy technologies has fundamentally transformed the global energy landscape over the past decade. Solar photovoltaic systems have achieved remarkable cost reductions, declining by approximately 89% since 2010, making them increasingly competitive with conventional fossil fuel sources. Wind energy has similarly experienced significant technological improvements, with larger turbine designs and improved capacity factors contributing to enhanced economic viability.",
    "In the realm of modern software engineering, the adoption of microservices architecture represents a paradigm shift from traditional monolithic application design. This architectural approach decomposes complex applications into independently deployable services, each responsible for specific business capabilities. The benefits include enhanced scalability, improved fault isolation, and the ability for development teams to work autonomously on individual components.",
    "The intersection of neuroscience and artificial intelligence continues to yield fascinating insights into both biological and computational intelligence. Recent research has demonstrated that deep neural networks, despite their architectural simplicity compared to biological brains, can develop internal representations remarkably similar to those observed in the visual cortex. These findings suggest fundamental computational principles that transcend implementation specifics.",
    "Effective project management requires a comprehensive understanding of both technical and interpersonal dynamics. Successful project managers must balance competing constraints including scope, timeline, budget, and quality while maintaining team morale and stakeholder satisfaction. The implementation of agile methodologies has significantly improved project outcomes by emphasizing iterative development, continuous feedback, and adaptive planning.",
    "The concept of sustainable urban development has gained unprecedented importance as cities worldwide grapple with the challenges of rapid population growth and climate change. Innovative approaches to urban planning, including green infrastructure, smart transportation systems, and energy-efficient building design, are being implemented to create more livable and resilient urban environments.",
]

ALL_HUMAN = HUMAN_TEXTS + HUMAN_TEXTS_LONG  # 15 total
ALL_AI = AI_TEXTS + AI_TEXTS_LONG          # 15 total

ENGINE_NAMES = ["bert_raid", "e5", "tmr", "fakespot"]

# Also test non-batch engines for accuracy comparison
NON_BATCH_ENGINES = ["openai", "chatgpt", "desklib", "superannotate", "remodetect"]


def load_engine(name):
    """Load an engine and return (engine_instance, load_time_ms)."""
    t0 = time.perf_counter()
    if name == "bert_raid":
        from app.engines.classifier_bert_raid import ClassifierBERTRaidEngine
        eng = ClassifierBERTRaidEngine()
    elif name == "e5":
        from app.engines.classifier_e5 import ClassifierE5Engine
        eng = ClassifierE5Engine()
    elif name == "tmr":
        from app.engines.classifier_tmr import ClassifierTMREngine
        eng = ClassifierTMREngine()
    elif name == "fakespot":
        from app.engines.classifier_fakespot import ClassifierFakespotEngine
        eng = ClassifierFakespotEngine()
    elif name == "openai":
        from app.engines.classifier_openai import ClassifierOpenAIEngine
        eng = ClassifierOpenAIEngine()
    elif name == "chatgpt":
        from app.engines.classifier_chatgpt import ClassifierChatGPTEngine
        eng = ClassifierChatGPTEngine()
    elif name == "desklib":
        from app.engines.classifier_desklib import ClassifierDesklibEngine
        eng = ClassifierDesklibEngine()
    elif name == "superannotate":
        from app.engines.classifier_superannotate import ClassifierSuperAnnotateEngine
        eng = ClassifierSuperAnnotateEngine()
    elif name == "remodetect":
        from app.engines.classifier_remodetect import ClassifierReMoDetectEngine
        eng = ClassifierReMoDetectEngine()
    else:
        raise ValueError(f"Unknown engine: {name}")
    # Warmup
    eng.analyze("warmup text for model loading and compilation")
    load_ms = (time.perf_counter() - t0) * 1000
    return eng, load_ms


def get_scores(eng, texts):
    """Get raw scores for a list of texts."""
    if hasattr(eng, 'analyze_batch'):
        return list(eng.analyze_batch(texts))
    else:
        return [eng.analyze(t).score for t in texts]


def bench_speed_batch(eng, texts, runs=5):
    """Benchmark batch speed. Returns (avg_ms, min_ms, max_ms)."""
    # Warmup
    get_scores(eng, texts[:2])
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        get_scores(eng, texts)
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.mean(times), min(times), max(times)


def compute_metrics(human_scores, ai_scores, threshold=0.5):
    """Compute classification metrics at a given threshold."""
    tp = sum(1 for s in ai_scores if s >= threshold)
    fn = sum(1 for s in ai_scores if s < threshold)
    fp = sum(1 for s in human_scores if s >= threshold)
    tn = sum(1 for s in human_scores if s < threshold)

    accuracy = (tp + tn) / (len(human_scores) + len(ai_scores))
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    avg_h = statistics.mean(human_scores) if human_scores else 0
    avg_a = statistics.mean(ai_scores) if ai_scores else 0

    return {
        "accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "avg_human": avg_h, "avg_ai": avg_a, "gap": avg_a - avg_h,
        "false_red_rate": fp / len(human_scores) if human_scores else 0,
    }


def test_weighted_combo(all_scores, weights, human_count, ai_count, threshold=0.5):
    """Test a weighted combination of engine scores."""
    total = human_count + ai_count
    combined = []
    for i in range(total):
        s = sum(all_scores[eng][i] * w for eng, w in weights.items())
        combined.append(s)
    return compute_metrics(combined[:human_count], combined[human_count:], threshold)


def find_optimal_threshold(human_scores, ai_scores):
    """Find the threshold that maximizes F1."""
    best_f1 = 0
    best_t = 0.5
    for t in [i/100 for i in range(20, 80)]:
        m = compute_metrics(human_scores, ai_scores, t)
        if m["f1"] > best_f1:
            best_f1 = m["f1"]
            best_t = t
    return best_t, best_f1


def main():
    print("=" * 100)
    print("COMPREHENSIVE ENGINE BENCHMARK — FINDING OPTIMAL SNIPPET SCORING")
    print("=" * 100)
    print(f"Short texts: {len(HUMAN_TEXTS)} human + {len(AI_TEXTS)} AI (100-210ch)")
    print(f"Long texts:  {len(HUMAN_TEXTS_LONG)} human + {len(AI_TEXTS_LONG)} AI (250-600ch)")
    print(f"Total: {len(ALL_HUMAN)} human + {len(ALL_AI)} AI = {len(ALL_HUMAN) + len(ALL_AI)} texts")
    print()

    # =====================================================================
    # PHASE 1: Load all batch engines, get raw scores for ALL texts
    # =====================================================================
    print("PHASE 1: Loading engines and collecting raw scores...")
    print("-" * 100)

    engines = {}
    raw_scores = {}    # raw_scores[engine_name] = list of 30 scores (15 human + 15 AI)
    speed_results = {} # speed_results[engine_name] = {batch5_avg, batch10_avg, ...}

    all_texts = ALL_HUMAN + ALL_AI  # 30 texts

    for name in ENGINE_NAMES:
        print(f"  Loading {name}...", end=" ", flush=True)
        eng, load_ms = load_engine(name)
        engines[name] = eng
        print(f"loaded in {load_ms:.0f}ms", end=" ", flush=True)

        # Get all scores
        scores = get_scores(eng, all_texts)
        raw_scores[name] = scores

        # Speed benchmarks
        batch5 = all_texts[:5]
        batch10 = all_texts[:10]
        avg5, mn5, mx5 = bench_speed_batch(eng, batch5)
        avg10, mn10, mx10 = bench_speed_batch(eng, batch10)
        avg20, mn20, mx20 = bench_speed_batch(eng, all_texts[:20])

        speed_results[name] = {
            "5": {"avg": avg5, "min": mn5, "max": mx5},
            "10": {"avg": avg10, "min": mn10, "max": mx10},
            "20": {"avg": avg20, "min": mn20, "max": mx20},
        }

        print(f"| speed: 5→{avg5:.0f}ms 10→{avg10:.0f}ms 20→{avg20:.0f}ms")

    # =====================================================================
    # PHASE 1b: Load non-batch engines for accuracy comparison
    # =====================================================================
    print()
    print("  Loading non-batch engines for comparison...")
    nb_scores = {}
    for name in NON_BATCH_ENGINES:
        try:
            print(f"  Loading {name}...", end=" ", flush=True)
            eng, load_ms = load_engine(name)
            scores = get_scores(eng, all_texts)
            nb_scores[name] = scores
            print(f"loaded in {load_ms:.0f}ms ✓")
        except Exception as e:
            print(f"FAILED: {e}")

    # =====================================================================
    # PHASE 2: Per-engine accuracy at different text lengths
    # =====================================================================
    print()
    print("=" * 100)
    print("PHASE 2: PER-ENGINE ACCURACY")
    print("=" * 100)

    # Full dataset (30 texts)
    print(f"\n{'Engine':<15} {'Acc%':>5} {'F1':>6} {'Prec':>6} {'Rec':>6} {'FP':>4} {'FN':>4} {'Gap':>6} {'AvgH':>6} {'AvgA':>6} | 5-batch ms")
    print("-" * 100)
    for name in ENGINE_NAMES + list(nb_scores.keys()):
        scores = raw_scores.get(name, nb_scores.get(name))
        if scores is None:
            continue
        m = compute_metrics(scores[:15], scores[15:])
        sp = speed_results.get(name, {}).get("5", {})
        sp_str = f"{sp['avg']:.0f}" if sp else "n/a"
        print(f"{name:<15} {m['accuracy']*100:>5.1f} {m['f1']:>6.3f} {m['precision']:>6.3f} {m['recall']:>6.3f} "
              f"{m['fp']:>4} {m['fn']:>4} {m['gap']:>6.3f} {m['avg_human']:>6.3f} {m['avg_ai']:>6.3f} | {sp_str}")

    # Short texts only (20 texts, original benchmark)
    print(f"\n--- Short texts only ({len(HUMAN_TEXTS)}h + {len(AI_TEXTS)}a, 100-210ch) ---")
    print(f"{'Engine':<15} {'Acc%':>5} {'F1':>6} {'FP':>4} {'FN':>4} {'Gap':>6} {'AvgH':>6} {'AvgA':>6}")
    print("-" * 80)
    for name in ENGINE_NAMES + list(nb_scores.keys()):
        scores = raw_scores.get(name, nb_scores.get(name))
        if scores is None:
            continue
        m = compute_metrics(scores[:10], scores[10:15])
        print(f"{name:<15} {m['accuracy']*100:>5.1f} {m['f1']:>6.3f} {m['fp']:>4} {m['fn']:>4} "
              f"{m['gap']:>6.3f} {m['avg_human']:>6.3f} {m['avg_ai']:>6.3f}")

    # Long texts only (10 texts)
    print(f"\n--- Long texts only ({len(HUMAN_TEXTS_LONG)}h + {len(AI_TEXTS_LONG)}a, 250-600ch) ---")
    print(f"{'Engine':<15} {'Acc%':>5} {'F1':>6} {'FP':>4} {'FN':>4} {'Gap':>6} {'AvgH':>6} {'AvgA':>6}")
    print("-" * 80)
    for name in ENGINE_NAMES + list(nb_scores.keys()):
        scores = raw_scores.get(name, nb_scores.get(name))
        if scores is None:
            continue
        # Long texts: human indices 10-14, AI indices 25-29
        m = compute_metrics(scores[10:15], scores[25:30])
        print(f"{name:<15} {m['accuracy']*100:>5.1f} {m['f1']:>6.3f} {m['fp']:>4} {m['fn']:>4} "
              f"{m['gap']:>6.3f} {m['avg_human']:>6.3f} {m['avg_ai']:>6.3f}")

    # =====================================================================
    # PHASE 3: Per-text score breakdown (all engines)
    # =====================================================================
    print()
    print("=" * 100)
    print("PHASE 3: PER-TEXT SCORES (raw probabilities)")
    print("=" * 100)

    all_engine_names = ENGINE_NAMES + list(nb_scores.keys())
    header = "     " + "  ".join(f"{n[:6]:>7}" for n in all_engine_names) + "  chars"
    print(header)
    print("-" * len(header))

    for i, text in enumerate(ALL_HUMAN):
        label = f"H{i:02d}"
        scores_str = "  ".join(
            f"{(raw_scores.get(n, nb_scores.get(n, []))[i] if i < len(raw_scores.get(n, nb_scores.get(n, []))) else 0):>7.3f}"
            for n in all_engine_names
        )
        print(f"{label}   {scores_str}  {len(text):>4}")
    print()
    for i, text in enumerate(ALL_AI):
        label = f"A{i:02d}"
        idx = 15 + i
        scores_str = "  ".join(
            f"{(raw_scores.get(n, nb_scores.get(n, []))[idx] if idx < len(raw_scores.get(n, nb_scores.get(n, []))) else 0):>7.3f}"
            for n in all_engine_names
        )
        print(f"{label}   {scores_str}  {len(text):>4}")

    # =====================================================================
    # PHASE 4: ALL COMBINATIONS (1, 2, 3, 4 engines) with equal weights
    # =====================================================================
    print()
    print("=" * 100)
    print("PHASE 4: ALL ENGINE COMBINATIONS (equal weight, threshold=0.50)")
    print("=" * 100)

    combo_results = []

    for r in range(1, len(ENGINE_NAMES) + 1):
        for combo in itertools.combinations(ENGINE_NAMES, r):
            # Equal weight
            weights = {n: 1.0 / len(combo) for n in combo}
            # Parallel latency = max of individual 5-batch times
            parallel_ms = max(speed_results[n]["5"]["avg"] for n in combo)

            m = test_weighted_combo(raw_scores, weights, 15, 15)

            combo_results.append({
                "engines": combo,
                "n_engines": len(combo),
                "weights": weights,
                "weight_label": "equal",
                "parallel_ms": parallel_ms,
                "metrics": m,
            })

    # Sort by F1 descending, then by fewer false positives
    combo_results.sort(key=lambda x: (-x["metrics"]["f1"], x["metrics"]["fp"], x["parallel_ms"]))

    print(f"\n{'#':>2} {'Combination':<35} {'N':>2} {'ms':>5} {'Acc%':>5} {'F1':>6} {'Prec':>6} {'Rec':>6} {'FP':>3} {'FN':>3} {'Gap':>6}")
    print("-" * 100)
    for i, c in enumerate(combo_results):
        m = c["metrics"]
        name = "+".join(c["engines"])
        print(f"{i+1:>2} {name:<35} {c['n_engines']:>2} {c['parallel_ms']:>5.0f} "
              f"{m['accuracy']*100:>5.1f} {m['f1']:>6.3f} {m['precision']:>6.3f} {m['recall']:>6.3f} "
              f"{m['fp']:>3} {m['fn']:>3} {m['gap']:>6.3f}")

    # =====================================================================
    # PHASE 5: WEIGHTED COMBINATIONS (optimized weights)
    # =====================================================================
    print()
    print("=" * 100)
    print("PHASE 5: OPTIMIZED WEIGHTING for top combinations")
    print("=" * 100)

    # For each promising combination, try many weight distributions
    # Focus on combos with F1 >= 0.8
    top_combos = [c for c in combo_results if c["metrics"]["f1"] >= 0.75]
    if not top_combos:
        top_combos = combo_results[:10]

    weight_results = []

    for c in top_combos:
        combo = c["engines"]
        n = len(combo)

        if n == 1:
            # Single engine: try different thresholds
            name = combo[0]
            scores_h = raw_scores[name][:15]
            scores_a = raw_scores[name][15:]
            best_t, best_f1 = find_optimal_threshold(scores_h, scores_a)
            m = compute_metrics(scores_h, scores_a, best_t)
            weight_results.append({
                "engines": combo,
                "weights": {name: 1.0},
                "threshold": best_t,
                "weight_label": f"single(t={best_t:.2f})",
                "parallel_ms": speed_results[name]["5"]["avg"],
                "metrics": m,
            })
            continue

        # Try weight distributions (step=0.05 for thoroughness)
        step = 0.05
        best_combo_f1 = 0
        best_combo_result = None

        if n == 2:
            for w1 in [i * step for i in range(1, int(1/step))]:
                w2 = round(1.0 - w1, 2)
                if w2 <= 0:
                    continue
                weights = {combo[0]: w1, combo[1]: w2}
                m = test_weighted_combo(raw_scores, weights, 15, 15)
                if m["f1"] > best_combo_f1 or (m["f1"] == best_combo_f1 and m["fp"] < best_combo_result["metrics"]["fp"]):
                    best_combo_f1 = m["f1"]
                    best_combo_result = {
                        "engines": combo, "weights": weights,
                        "weight_label": f"{w1:.2f}/{w2:.2f}",
                        "parallel_ms": max(speed_results[n2]["5"]["avg"] for n2 in combo),
                        "metrics": m,
                    }
                # Also try with optimal threshold
                combined_h = [sum(raw_scores[e][i] * w for e, w in weights.items()) for i in range(15)]
                combined_a = [sum(raw_scores[e][15+i] * w for e, w in weights.items()) for i in range(15)]
                opt_t, opt_f1 = find_optimal_threshold(combined_h, combined_a)
                m2 = compute_metrics(combined_h, combined_a, opt_t)
                if m2["f1"] > best_combo_f1 or (m2["f1"] == best_combo_f1 and m2["fp"] < (best_combo_result or {"metrics": {"fp": 999}})["metrics"]["fp"]):
                    best_combo_f1 = m2["f1"]
                    best_combo_result = {
                        "engines": combo, "weights": weights,
                        "weight_label": f"{w1:.2f}/{w2:.2f}(t={opt_t:.2f})",
                        "parallel_ms": max(speed_results[n2]["5"]["avg"] for n2 in combo),
                        "metrics": m2, "threshold": opt_t,
                    }

        elif n == 3:
            for w1 in [i * 0.10 for i in range(1, 10)]:
                for w2 in [i * 0.10 for i in range(1, int((1.0 - w1) / 0.10) + 1)]:
                    w3 = round(1.0 - w1 - w2, 2)
                    if w3 <= 0:
                        continue
                    weights = {combo[0]: w1, combo[1]: w2, combo[2]: w3}
                    m = test_weighted_combo(raw_scores, weights, 15, 15)
                    if m["f1"] > best_combo_f1 or (m["f1"] == best_combo_f1 and m["fp"] < (best_combo_result or {"metrics": {"fp": 999}})["metrics"]["fp"]):
                        best_combo_f1 = m["f1"]
                        best_combo_result = {
                            "engines": combo, "weights": weights,
                            "weight_label": "/".join(f"{weights[e]:.2f}" for e in combo),
                            "parallel_ms": max(speed_results[n2]["5"]["avg"] for n2 in combo),
                            "metrics": m,
                        }

        elif n == 4:
            for w1 in [i * 0.10 for i in range(1, 8)]:
                for w2 in [i * 0.10 for i in range(1, int((1.0 - w1) / 0.10) + 1)]:
                    for w3 in [i * 0.10 for i in range(1, int((1.0 - w1 - w2) / 0.10) + 1)]:
                        w4 = round(1.0 - w1 - w2 - w3, 2)
                        if w4 <= 0:
                            continue
                        weights = {combo[0]: w1, combo[1]: w2, combo[2]: w3, combo[3]: w4}
                        m = test_weighted_combo(raw_scores, weights, 15, 15)
                        if m["f1"] > best_combo_f1 or (m["f1"] == best_combo_f1 and m["fp"] < (best_combo_result or {"metrics": {"fp": 999}})["metrics"]["fp"]):
                            best_combo_f1 = m["f1"]
                            best_combo_result = {
                                "engines": combo, "weights": weights,
                                "weight_label": "/".join(f"{weights[e]:.2f}" for e in combo),
                                "parallel_ms": max(speed_results[n2]["5"]["avg"] for n2 in combo),
                                "metrics": m,
                            }

        if best_combo_result:
            weight_results.append(best_combo_result)

    # Sort by F1
    weight_results.sort(key=lambda x: (-x["metrics"]["f1"], x["metrics"]["fp"]))

    print(f"\n{'Combination':<35} {'Weights':<30} {'ms':>5} {'F1':>6} {'Prec':>6} {'FP':>3} {'FN':>3} {'Gap':>6}")
    print("-" * 110)
    for wr in weight_results:
        m = wr["metrics"]
        name = "+".join(wr["engines"])
        print(f"{name:<35} {wr['weight_label']:<30} {wr['parallel_ms']:>5.0f} "
              f"{m['f1']:>6.3f} {m['precision']:>6.3f} {m['fp']:>3} {m['fn']:>3} {m['gap']:>6.3f}")

    # =====================================================================
    # PHASE 6: Per-text-length analysis for top combos
    # =====================================================================
    print()
    print("=" * 100)
    print("PHASE 6: TEXT LENGTH SENSITIVITY")
    print("=" * 100)

    # Test how each engine performs when text is truncated
    truncation_lengths = [80, 100, 120, 150, 200, 300, 500]

    print("\nPer-engine FP rate (% of human texts scoring >= 0.50) at different truncation lengths:")
    print(f"{'Engine':<15}", end="")
    for tl in truncation_lengths:
        print(f" {tl:>5}ch", end="")
    print()
    print("-" * (15 + 7 * len(truncation_lengths)))

    for name in ENGINE_NAMES:
        eng = engines[name]
        print(f"{name:<15}", end="")
        for tl in truncation_lengths:
            trunc_human = [t[:tl] for t in ALL_HUMAN if len(t) >= tl]
            if not trunc_human:
                print(f" {'n/a':>5}", end="")
                continue
            scores = get_scores(eng, trunc_human)
            fp_rate = sum(1 for s in scores if s >= 0.5) / len(scores)
            print(f" {fp_rate*100:>4.0f}%", end="")
        print()

    print("\nPer-engine detection rate (% of AI texts scoring >= 0.50) at different truncation lengths:")
    print(f"{'Engine':<15}", end="")
    for tl in truncation_lengths:
        print(f" {tl:>5}ch", end="")
    print()
    print("-" * (15 + 7 * len(truncation_lengths)))

    for name in ENGINE_NAMES:
        eng = engines[name]
        print(f"{name:<15}", end="")
        for tl in truncation_lengths:
            trunc_ai = [t[:tl] for t in ALL_AI if len(t) >= tl]
            if not trunc_ai:
                print(f" {'n/a':>5}", end="")
                continue
            scores = get_scores(eng, trunc_ai)
            det_rate = sum(1 for s in scores if s >= 0.5) / len(scores)
            print(f" {det_rate*100:>4.0f}%", end="")
        print()

    # Detailed per-text analysis at key truncation points
    for tl in [100, 150, 300, 500]:
        print(f"\n--- Detailed scores at {tl}ch truncation ---")
        trunc_h = [(i, t[:tl]) for i, t in enumerate(ALL_HUMAN) if len(t) >= tl]
        trunc_a = [(i, t[:tl]) for i, t in enumerate(ALL_AI) if len(t) >= tl]

        if not trunc_h and not trunc_a:
            print("  No texts long enough")
            continue

        # Get scores for truncated texts
        all_trunc = [t for _, t in trunc_h] + [t for _, t in trunc_a]
        eng_scores = {}
        for name in ENGINE_NAMES:
            eng_scores[name] = get_scores(engines[name], all_trunc)

        header = f"  {'ID':>4} {'ch':>4} " + " ".join(f"{n[:6]:>7}" for n in ENGINE_NAMES) + "  avg    label"
        print(header)

        for j, (i, text) in enumerate(trunc_h):
            scores = [eng_scores[n][j] for n in ENGINE_NAMES]
            avg = statistics.mean(scores)
            fp_flag = " FP!" if avg >= 0.5 else ""
            print(f"  H{i:02d} {len(text):>4} " + " ".join(f"{s:>7.3f}" for s in scores) + f"  {avg:.3f}  human{fp_flag}")

        offset = len(trunc_h)
        for j, (i, text) in enumerate(trunc_a):
            scores = [eng_scores[n][offset + j] for n in ENGINE_NAMES]
            avg = statistics.mean(scores)
            fn_flag = " MISS" if avg < 0.5 else ""
            print(f"  A{i:02d} {len(text):>4} " + " ".join(f"{s:>7.3f}" for s in scores) + f"  {avg:.3f}  AI{fn_flag}")

    # =====================================================================
    # PHASE 7: FAKESPOT RELIABILITY ANALYSIS
    # =====================================================================
    print()
    print("=" * 100)
    print("PHASE 7: FAKESPOT RELIABILITY BY TEXT LENGTH")
    print("=" * 100)

    fs_eng = engines["fakespot"]
    print("\nFakespot score distribution on HUMAN texts at different truncation lengths:")
    for tl in [80, 100, 120, 150, 200, 300, 500]:
        trunc = [t[:tl] for t in ALL_HUMAN if len(t) >= tl]
        if not trunc:
            continue
        scores = get_scores(fs_eng, trunc)
        high = sum(1 for s in scores if s >= 0.50)
        med = sum(1 for s in scores if 0.30 <= s < 0.50)
        low = sum(1 for s in scores if s < 0.30)
        print(f"  {tl:>4}ch ({len(trunc):>2} texts): low(<0.30)={low:>2}  med(0.30-0.49)={med:>2}  high(>=0.50)={high:>2}  "
              f"FP_rate={high/len(trunc)*100:.0f}%  scores={[round(s, 3) for s in sorted(scores)]}")

    print("\nFakespot score distribution on AI texts at different truncation lengths:")
    for tl in [80, 100, 120, 150, 200, 300, 500]:
        trunc = [t[:tl] for t in ALL_AI if len(t) >= tl]
        if not trunc:
            continue
        scores = get_scores(fs_eng, trunc)
        high = sum(1 for s in scores if s >= 0.50)
        med = sum(1 for s in scores if 0.30 <= s < 0.50)
        low = sum(1 for s in scores if s < 0.30)
        print(f"  {tl:>4}ch ({len(trunc):>2} texts): low(<0.30)={low:>2}  med(0.30-0.49)={med:>2}  high(>=0.50)={high:>2}  "
              f"det_rate={high/len(trunc)*100:.0f}%  scores={[round(s, 3) for s in sorted(scores)]}")

    # =====================================================================
    # PHASE 8: OPTIMAL SCORING FUNCTION SIMULATION
    # =====================================================================
    print()
    print("=" * 100)
    print("PHASE 8: SCORING FUNCTION SIMULATION")
    print("=" * 100)
    print("Testing different scoring strategies on all 30 texts at original length...")

    strategies = {}

    # Strategy 1: Equal weight all 4
    def s_equal(b, e, t, f, tl):
        return (b + e + t + f) / 4
    strategies["equal_4"] = s_equal

    # Strategy 2: Fakespot-dominant (current quick-score style)
    def s_fs_dom(b, e, t, f, tl):
        return f * 0.50 + e * 0.25 + t * 0.15 + b * 0.10
    strategies["fs_dominant"] = s_fs_dom

    # Strategy 3: E5-dominant
    def s_e5_dom(b, e, t, f, tl):
        return e * 0.50 + f * 0.30 + t * 0.10 + b * 0.10
    strategies["e5_dominant"] = s_e5_dom

    # Strategy 4: Fakespot + E5 only (2 engines)
    def s_fs_e5(b, e, t, f, tl):
        return f * 0.65 + e * 0.35
    strategies["fs+e5_only"] = s_fs_e5

    # Strategy 5: Adaptive (current implementation)
    def s_adaptive(b, e, t, f, tl):
        if tl < 150:
            if f < 0.30:
                score = f * 0.70 + e * 0.30
                return min(score, 0.40)
            elif f < 0.50:
                score = f * 0.50 + e * 0.25 + t * 0.15 + b * 0.10
                return min(score, 0.45)
            else:
                score = f * 0.40 + e * 0.25 + t * 0.15 + b * 0.20
                return min(score, 0.50)
        elif f >= 0.50:
            if tl >= 300:
                if e > 0.60:
                    score = f * 0.45 + e * 0.30 + t * 0.15 + b * 0.10
                else:
                    score = f * 0.55 + e * 0.20 + t * 0.15 + b * 0.10
            else:
                if f >= 0.70 and e >= 0.70:
                    score = f * 0.40 + e * 0.30 + t * 0.15 + b * 0.15
                else:
                    score = f * 0.40 + e * 0.25 + t * 0.15 + b * 0.20
                    score = min(score, 0.65)
            if e > 0.85 and f > 0.85 and t > 0.85 and b > 0.85:
                score = score * 0.75 + 0.50 * 0.25
            return score
        elif tl >= 300:
            if f >= 0.35:
                return f * 0.50 + e * 0.25 + t * 0.15 + b * 0.10
            elif e < 0.60:
                return f * 0.40 + e * 0.30 + t * 0.15 + b * 0.15
            else:
                return min(f * 0.35 + e * 0.35 + t * 0.15 + b * 0.15, 0.45)
        else:
            if e > 0.75 and t > 0.80:
                return min(e * 0.45 + t * 0.30 + b * 0.10 + f * 0.15, 0.55)
            elif e > 0.75:
                return min(e * 0.40 + 0.05, 0.50)
            elif e < 0.50:
                return e * 0.40 + f * 0.30 + t * 0.15 + b * 0.15
            else:
                return min(e * 0.35 + f * 0.25 + t * 0.20 + b * 0.20, 0.45)
    strategies["adaptive_v2"] = s_adaptive

    # Strategy 6: Fakespot veto — only score red if fakespot agrees
    def s_fs_veto(b, e, t, f, tl):
        avg = (b + e + t + f) / 4
        if f < 0.40:
            return min(avg, 0.45)  # Fakespot says no → cap
        return avg
    strategies["fs_veto"] = s_fs_veto

    # Strategy 7: Max of (fakespot, e5) — simple max
    def s_max_fs_e5(b, e, t, f, tl):
        return max(f, e)
    strategies["max_fs_e5"] = s_max_fs_e5

    # Strategy 8: Fakespot gate — use fakespot as gate, e5+tmr for score
    def s_fs_gate(b, e, t, f, tl):
        if f >= 0.50:
            return f * 0.50 + e * 0.30 + t * 0.20
        elif f >= 0.30:
            return min((e * 0.40 + t * 0.30 + f * 0.30), 0.50)
        else:
            return min(f * 0.60 + e * 0.30 + t * 0.10, 0.35)
    strategies["fs_gate"] = s_fs_gate

    # Strategy 9: Adaptive V3 — trust Fakespot-LOW even more
    def s_adaptive_v3(b, e, t, f, tl):
        # Core insight: Fakespot-LOW is reliable at all lengths
        # Fakespot-HIGH only reliable at 150ch+
        if f < 0.25:
            # Fakespot says human (reliable signal)
            if e < 0.50:
                return f * 0.60 + e * 0.40  # Both agree human
            else:
                return min(f * 0.60 + e * 0.40, 0.35)  # Fakespot anchors
        elif f < 0.50:
            # Fakespot uncertain
            return min(f * 0.40 + e * 0.30 + t * 0.15 + b * 0.15, 0.45)
        else:
            # Fakespot says AI
            if tl < 150:
                return min(f * 0.40 + e * 0.25 + t * 0.15 + b * 0.20, 0.50)
            elif e > 0.60:
                return f * 0.45 + e * 0.30 + t * 0.15 + b * 0.10
            else:
                return f * 0.55 + e * 0.20 + t * 0.15 + b * 0.10
    strategies["adaptive_v3"] = s_adaptive_v3

    # Evaluate all strategies
    print(f"\n{'Strategy':<20} {'Acc%':>5} {'F1':>6} {'Prec':>6} {'Rec':>6} {'FP':>3} {'FN':>3} {'FR%':>5} {'Gap':>6}  FalseReds")
    print("-" * 105)

    for sname, sfunc in strategies.items():
        human_scores = []
        ai_scores = []
        false_reds = []

        for i in range(15):
            b = raw_scores["bert_raid"][i]
            e = raw_scores["e5"][i]
            t = raw_scores["tmr"][i]
            f = raw_scores["fakespot"][i]
            tl = len(ALL_HUMAN[i])
            score = sfunc(b, e, t, f, tl)
            human_scores.append(score)
            if score >= 0.65:
                false_reds.append(f"H{i:02d}({score*100:.0f}%)")

        for i in range(15):
            b = raw_scores["bert_raid"][15 + i]
            e = raw_scores["e5"][15 + i]
            t = raw_scores["tmr"][15 + i]
            f = raw_scores["fakespot"][15 + i]
            tl = len(ALL_AI[i])
            score = sfunc(b, e, t, f, tl)
            ai_scores.append(score)

        m = compute_metrics(human_scores, ai_scores)
        fr_str = ", ".join(false_reds) if false_reds else "none"
        print(f"{sname:<20} {m['accuracy']*100:>5.1f} {m['f1']:>6.3f} {m['precision']:>6.3f} {m['recall']:>6.3f} "
              f"{m['fp']:>3} {m['fn']:>3} {m['false_red_rate']*100:>4.0f}% {m['gap']:>6.3f}  {fr_str}")

    # =====================================================================
    # PHASE 9: FINAL RECOMMENDATION
    # =====================================================================
    print()
    print("=" * 100)
    print("PHASE 9: FINAL RECOMMENDATION")
    print("=" * 100)

    # Summarize timing
    print("\nEngine timing (5-text batch, avg of 5 runs):")
    for name in ENGINE_NAMES:
        s = speed_results[name]["5"]
        print(f"  {name:<12}: {s['avg']:>6.0f}ms (min={s['min']:.0f} max={s['max']:.0f})")

    print("\nParallel execution timing:")
    for r in range(1, 5):
        for combo in itertools.combinations(ENGINE_NAMES, r):
            ms = max(speed_results[n]["5"]["avg"] for n in combo)
            print(f"  {'+'.join(combo):<35}: {ms:>5.0f}ms")

    # Save raw data for analysis
    output = {
        "raw_scores": {k: [round(s, 4) for s in v] for k, v in raw_scores.items()},
        "nb_scores": {k: [round(s, 4) for s in v] for k, v in nb_scores.items()},
        "speed": speed_results,
        "text_lengths": {
            "human": [len(t) for t in ALL_HUMAN],
            "ai": [len(t) for t in ALL_AI],
        },
    }
    with open("/tmp/bench_full_data.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nRaw data saved to /tmp/bench_full_data.json")
    print("=" * 100)


if __name__ == "__main__":
    main()
