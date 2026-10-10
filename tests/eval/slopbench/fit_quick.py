"""Fit the quick path (/api/quick-score, /api/paragraph-score) on SlopBench.

Same model and method as fit.py, restricted to the engines the quick path runs:
a logistic model with non-negative weights over their logits, short texts pulled
toward a neutral score, band edges placed where a measured share of human text
begins, every reported number leave-one-source-out. Writes the "quick" section
of app/calibration.json.

Usage: python fit_quick.py results.jsonl [results-short.jsonl ...] > report.md
"""

import sys

import numpy as np
from sklearn.metrics import roc_auc_score

import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from app.config import QUICK_AI_MIN, QUICK_CLEAN_MAX  # noqa: E402
from fit import (  # noqa: E402
    CALLED_AI,
    FLAGGED,
    TRAIN_AS_AI,
    band_knots,
    fit_length,
    fit_weights,
    load,
    matrix,
    rate,
    sample_weights,
    to_score,
    write_section,
    z_values,
)

# Display names in the results files, as app/analyzer.py's _quick_engines plus
# the two regex heuristics the quick path reads.
QUICK = {
    "Fakespot": "classifier_fakespot",
    "TMR Detector": "classifier_tmr",
    "BERT-tiny RAID": "classifier_bert_raid",
    "E5-Small": "classifier_e5",
    "Linguistic Markers": "linguistic",
    "Formulaic Patterns": "formulaic",
}


def main() -> None:
    rows = load(sys.argv[1:])
    for r in rows:
        if r["label"] == "human":
            r["y"] = 0
        elif r["label"] == "ai" and r.get("variant", "") in ("", *TRAIN_AS_AI):
            r["y"] = 1
        else:
            r["y"] = None
    full = [r for r in rows if r["y"] is not None and "cut" not in r]
    cut = [r for r in rows if r["y"] is not None and "cut" in r]
    engines = list(QUICK)

    X, y = matrix(full, engines), np.array([r["y"] for r in full], float)
    words = np.array([r.get("words", 300) for r in full], float)
    w = sample_weights(full)
    sources = sorted({r["source"] for r in full})

    theta = fit_weights(X, y, w)
    k, neutral = 0.0, 0.0
    if cut:
        Xc, yc = matrix(cut, engines), np.array([r["y"] for r in cut], float)
        k, neutral = fit_length(
            theta, Xc, yc, np.array([r["cut"] for r in cut], float), sample_weights(cut)
        )

    held_z = np.zeros(len(full))
    for source in sources:
        test = np.array([r["source"] == source for r in full])
        fold = fit_weights(X[~test], y[~test], w[~test])
        held_z[test] = z_values(fold, X[test], words[test], k, neutral)
    human = [i for i, r in enumerate(full) if r["y"] == 0]
    knots = band_knots(held_z[human], [full[i]["source"] for i in human])
    held = to_score(held_z, knots)

    print("# Quick path calibration on SlopBench\n")
    print(
        f"{int((y == 0).sum())} human and {int((y == 1).sum())} AI texts, leave-one-source-out.\n"
    )
    print(
        "| | AUC | AI flagged (>45) | AI called AI (≥55) | Human flagged (>45) | Human called AI (≥55) |"
    )
    print("|---|---|---|---|---|---|")
    print(
        f"| Quick, fitted (held out) | {roc_auc_score(y, held):.3f} | {rate(held[y == 1], FLAGGED)} "
        f"| {rate(held[y == 1], CALLED_AI - 1e-9)} | {rate(held[y == 0], FLAGGED)} | {rate(held[y == 0], CALLED_AI - 1e-9)} |"
    )
    print(
        f"\nAt the quick verdict edges (clean ≤{QUICK_CLEAN_MAX}, ai >{QUICK_AI_MIN}): "
        f"human called ai {rate(held[y == 0], QUICK_AI_MIN)}, human clean {100 * (held[y == 0] <= QUICK_CLEAN_MAX).mean():.1f}%, "
        f"AI called ai {rate(held[y == 1], QUICK_AI_MIN)}."
    )
    print("\n## Human texts by source (flagged >45 / called AI ≥55)\n")
    print("| Source | n | >45 | ≥55 |")
    print("|---|---|---|---|")
    for source in sources:
        m = np.array([r["source"] == source for r in full]) & (y == 0)
        if m.any():
            print(
                f"| {source} | {int(m.sum())} | {rate(held[m], FLAGGED)} | {rate(held[m], CALLED_AI - 1e-9)} |"
            )
    print(f"\nShort texts: k = {k:.0f}, neutral = {neutral:.2f}\n")
    print("| Engine | Weight |")
    print("|---|---|")
    for name, value in sorted(zip(engines, theta[1:]), key=lambda kv: -kv[1]):
        print(f"| {name} | {value:.3f} |")

    write_section(
        "quick",
        {
            "intercept": round(float(theta[0]), 4),
            "weights": {
                QUICK[name]: round(float(v), 4) for name, v in zip(engines, theta[1:])
            },
            "length_k": k,
            "length_neutral": round(neutral, 4),
            "band_knots": knots,
        },
    )


if __name__ == "__main__":
    main()
