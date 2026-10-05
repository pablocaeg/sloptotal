"""Summarise a SlopBench run as Markdown tables.

Headline: AUC of AI against human text, and how much AI is caught when the
threshold is set so that only 1% or 5% of human text is flagged. Then the
production bands: how often each kind of human text is flagged (scores above
45) or called AI (55 and above), which is where fairness shows, for non-native
writers above all. Then detection by generating model, by adversarial variant,
and each engine on its own.

Usage: python analyze.py results.jsonl
"""

import json
import sys
from collections import defaultdict
from statistics import mean, median

FLAGGED = 45
CALLED_AI = 55


def auc(positives: list[float], negatives: list[float]) -> float | None:
    if not positives or not negatives:
        return None
    ranked = sorted([(s, 1) for s in positives] + [(s, 0) for s in negatives])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        average_rank = (i + j + 1) / 2
        rank_sum += average_rank * sum(label for _, label in ranked[i:j])
        i = j
    n_pos, n_neg = len(positives), len(negatives)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def threshold_at_fpr(human: list[float], fpr: float) -> float:
    ordered = sorted(human, reverse=True)
    return ordered[int(len(ordered) * fpr)] if ordered else 100.0


def share(scores: list[float], cut: float) -> str:
    hit = sum(s > cut for s in scores)
    return f"{100 * hit / len(scores):.1f}% ({hit}/{len(scores)})" if scores else "–"


def fmt(value: float | None) -> str:
    return "–" if value is None else f"{value:.3f}"


def main() -> None:
    rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
    base = [r for r in rows if "variant" not in r and r["label"] in ("human", "ai")]
    human = [r["overall"] for r in base if r["label"] == "human"]
    ai = [r["overall"] for r in base if r["label"] == "ai"]
    at1, at5 = threshold_at_fpr(human, 0.01), threshold_at_fpr(human, 0.05)

    print(f"## SlopBench: {len(human)} human, {len(ai)} AI, {len(rows) - len(base)} hard-case samples\n")
    print("| AUC | AI caught at 1% FPR | AI caught at 5% FPR | AI flagged (>45) | Human flagged (>45) | Human called AI (≥55) |")
    print("|---|---|---|---|---|---|")
    print(
        f"| {fmt(auc(ai, human))} | {share(ai, at1)} | {share(ai, at5)} | {share(ai, FLAGGED)} "
        f"| {share(human, FLAGGED)} | {share(human, CALLED_AI - 1e-9)} |\n"
    )

    print("### By source\n")
    print("| Source | Human | AI | AUC | AI flagged (>45) | Human flagged (>45) | Human called AI (≥55) | Median human / AI |")
    print("|---|---|---|---|---|---|---|---|")
    by_source: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in base:
        by_source[r["source"]][r["label"]].append(r["overall"])
    for source, groups in sorted(by_source.items()):
        h, a = groups["human"], groups["ai"]
        medians = f"{median(h):.1f} / {median(a):.1f}" if h and a else (f"{median(h):.1f} / –" if h else "–")
        print(
            f"| {source} | {len(h)} | {len(a)} | {fmt(auc(a, h))} | {share(a, FLAGGED)} "
            f"| {share(h, FLAGGED)} | {share(h, CALLED_AI - 1e-9)} | {medians} |"
        )

    print("\n### By generating model\n")
    print("| Model | Samples | AUC vs all human | Flagged (>45) | Median score |")
    print("|---|---|---|---|---|")
    by_model: dict[str, list[float]] = defaultdict(list)
    for r in base:
        if r["label"] == "ai":
            by_model[r["model"]].append(r["overall"])
    for model, scores in sorted(by_model.items(), key=lambda kv: -auc(kv[1], human)):
        print(f"| {model} | {len(scores)} | {fmt(auc(scores, human))} | {share(scores, FLAGGED)} | {median(scores):.1f} |")

    variants: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if "variant" in r:
            variants[r["variant"]].append(r)
    if variants:
        print("\n### Hard cases\n")
        print("| Variant | Label | Samples | Flagged (>45) | Called AI (≥55) | Median score | Median of the unmodified base |")
        print("|---|---|---|---|---|---|---|")
        base_score = {r["id"]: r["overall"] for r in base}
        for variant, items in sorted(variants.items()):
            scores = [r["overall"] for r in items]
            originals = [base_score[r["base"]] for r in items if r["base"] in base_score]
            print(
                f"| {variant} | {items[0]['label']} | {len(items)} | {share(scores, FLAGGED)} "
                f"| {share(scores, CALLED_AI - 1e-9)} | {median(scores):.1f} | {median(originals):.1f} |"
                if originals
                else f"| {variant} | {items[0]['label']} | {len(items)} | {share(scores, FLAGGED)} "
                f"| {share(scores, CALLED_AI - 1e-9)} | {median(scores):.1f} | – |"
            )

    print("\n### Each engine on its own (AUC, AI vs human)\n")
    engines = sorted({name for r in base for name in r["engines"]})
    table = []
    for name in engines:
        h = [r["engines"][name] for r in base if r["label"] == "human" and name in r["engines"]]
        a = [r["engines"][name] for r in base if r["label"] == "ai" and name in r["engines"]]
        table.append((auc(a, h) or 0, name, mean(h) if h else 0, mean(a) if a else 0))
    print("| Engine | AUC | Mean human | Mean AI |")
    print("|---|---|---|---|")
    for value, name, h, a in sorted(table, reverse=True):
        print(f"| {name} | {value:.3f} | {h:.3f} | {a:.3f} |")


if __name__ == "__main__":
    main()
