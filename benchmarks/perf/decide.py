"""Turn large_models.py output into a decision table.

For each variant: seconds per text length on the critical path (the slowest of
the three large models, since the engines run in parallel), how far each
engine's score moves against the current code, and how many final verdicts
change once the production calibration (app/calibration.py) is applied.

Usage: python benchmarks/perf/decide.py texts.json large_models_out.json [retime_out.json]

With retime.py's output as a third argument, the timing table uses its
interleaved timings instead of large_models.py's.
"""

import json
import random
import sys
from collections import defaultdict
from statistics import mean

from app.calibration import calibrated_score
from app.schemas import score_to_verdict_str

accuracy = json.load(open(sys.argv[1]))["accuracy"]
texts = {t["id"]: t for t in accuracy}
INT8_SAMPLE = set(random.Random(0).sample([t["id"] for t in accuracy], 60))
run = json.load(open(sys.argv[2]))
LARGE = ["classifier_desklib", "classifier_remodetect", "classifier_superannotate"]


def band(score: float) -> str:
    return score_to_verdict_str(score).split(" — ")[0]


def auc(pos, neg):
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


timing = defaultdict(lambda: defaultdict(list))
for t in (json.load(open(sys.argv[3])) if len(sys.argv) > 3 else run)["timing"]:
    timing[t["variant"]][(t["words"], t["engine"])].append(t["seconds"])

variants = list(run["scores"])
lengths = sorted({w for w, _ in timing["baseline"]})
print("Critical path, seconds (slowest large model, mean of a human and an AI text)\n")
print("| Variant | " + " | ".join(f"{w} words" for w in lengths) + " |")
print("|---|" + "---|" * len(lengths))
for v in [v for v in variants if v in timing]:
    cells = [max(mean(timing[v][(w, e)]) for e in LARGE) for w in lengths]
    print(f"| {v} | " + " | ".join(f"{c:.1f}" for c in cells) + " |")

baseline = run["scores"]["baseline"]
final = {}
for v in variants:
    final[v] = {}
    for tid, t in texts.items():
        engines = dict(t["engines"])
        for e in LARGE:
            engines[e] = run["scores"][v][e][tid]
        final[v][tid] = calibrated_score(engines, t["text"])[0]

print("\nAgainst the current code\n")
print("int8 is measured on its 60-text sample, every other variant on all texts.\n")
print("| Variant | Texts | Engine Δ mean | Engine Δ p95 | Engine Δ max | Overall Δ mean | Overall Δ max | Verdicts changed (SlopBench / users) | SlopBench AUC (baseline on same texts) |")
print("|---|---|---|---|---|---|---|---|---|")
for v in variants:
    ids = [t for t in texts if v != "int8" or t in INT8_SAMPLE]
    deltas = sorted(abs(run["scores"][v][e][tid] - baseline[e][tid]) for e in LARGE for tid in ids)
    overall = [abs(final[v][tid] - final["baseline"][tid]) for tid in ids]
    flips_bench = sum(band(final[v][t]) != band(final["baseline"][t]) for t in ids if texts[t]["label"] != "user")
    flips_users = sum(band(final[v][t]) != band(final["baseline"][t]) for t in ids if texts[t]["label"] == "user")
    pos = [final[v][t] for t in ids if texts[t]["label"] == "ai"]
    neg = [final[v][t] for t in ids if texts[t]["label"] == "human"]
    base_auc = auc([final["baseline"][t] for t in ids if texts[t]["label"] == "ai"],
                   [final["baseline"][t] for t in ids if texts[t]["label"] == "human"])
    print(f"| {v} | {len(ids)} | {mean(deltas):.3f} | {deltas[int(len(deltas) * 0.95)]:.3f} | {deltas[-1]:.3f} "
          f"| {mean(overall):.2f} | {max(overall):.1f} | {flips_bench} / {flips_users} | {auc(pos, neg):.3f} ({base_auc:.3f}) |")
