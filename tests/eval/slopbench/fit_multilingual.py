"""Fit the non-English calibration and write its section of app/calibration.json.

One set of engine weights for every non-English language (the English
SlopBench weights do not transfer: ReMoDetect is the only classifier that keeps
working across scripts), plus an offset per language, because the same text
quality lands on a different part of the scale in each language. Each offset
is set so that about 5% of that language's human text scores above 45.

Every number reported is from 5-fold cross-validation within each language;
a second table fits on DeepSeek text only and scores the other model families,
which says whether the weights learned machine text or one model's habits.

A language is "supported" when its held-out AUC is at least 0.90 and it
catches at least 60% of AI text at 45, "experimental" from AUC 0.80, and
"unsupported" below that.

Usage: python fit_multilingual.py ../multilingual/results.jsonl > report.md
"""

import json
import sys

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from fit import ENGINE_KEYS, FLAGGED, fit_weights, matrix, sample_weights, write_section

TARGET_FPR = 0.05
SUPPORTED_AUC, EXPERIMENTAL_AUC, SUPPORTED_RECALL = 0.90, 0.80, 0.60


def offsets(z: np.ndarray, y: np.ndarray, lang: np.ndarray) -> dict[str, float]:
    """Per language, the shift that puts TARGET_FPR of its human text above 45."""
    cut = float(np.log(FLAGGED / (100 - FLAGGED)))
    return {L: cut - float(np.quantile(z[(lang == L) & (y == 0)], 1 - TARGET_FPR)) for L in sorted(set(lang))}


def to_score(z: np.ndarray) -> np.ndarray:
    return 100 / (1 + np.exp(-z))


def rate(xs: np.ndarray) -> str:
    return f"{100 * np.mean(xs > FLAGGED):.0f}%" if len(xs) else "–"


def main() -> None:
    rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
    for r in rows:
        r["y"] = 1 if r["label"] == "ai" else 0
        r["source"] = f"{r['lang']}:{r['label']}"
    engines = sorted({e for r in rows for e in r["engines"]})
    X, y = matrix(rows, engines), np.array([r["y"] for r in rows], float)
    lang = np.array([r["lang"] for r in rows])
    deepseek = np.array([r["label"] == "human" or "deepseek" in r["model"] for r in rows])
    w = sample_weights(rows)

    held = np.zeros(len(rows))
    folds = StratifiedKFold(5, shuffle=True, random_state=0).split(X, [f"{a}{b}" for a, b in zip(lang, y)])
    for train, test in folds:
        theta = fit_weights(X[train], y[train], w[train])
        shift = offsets(theta[0] + X[train] @ theta[1:], y[train], lang[train])
        z = theta[0] + X[test] @ theta[1:]
        held[test] = to_score(z + np.array([shift[L] for L in lang[test]]))

    theta = fit_weights(X[deepseek], y[deepseek], w[deepseek])
    shift = offsets(theta[0] + X[deepseek] @ theta[1:], y[deepseek], lang[deepseek])
    cross = to_score(theta[0] + X @ theta[1:] + np.array([shift[L] for L in lang]))

    current = np.array([r["overall"] for r in rows])
    print("# Non-English calibration\n")
    print(f"{int((y == 0).sum())} human and {int((y == 1).sum())} AI texts in {len(set(lang))} languages; "
          "5-fold cross-validation within each language.\n")
    print("| Language | AUC, current | AUC, fitted | AI flagged, current | AI flagged, fitted "
          "| Human flagged, current | Human flagged, fitted | Other models flagged (fit on DeepSeek) | Status |")
    print("|---|---|---|---|---|---|---|---|---|")
    status: dict[str, str] = {}
    for L in sorted(set(lang)):
        m = lang == L
        auc_fit = roc_auc_score(y[m], held[m])
        recall = np.mean(held[m & (y == 1)] > FLAGGED)
        status[L] = (
            "supported" if auc_fit >= SUPPORTED_AUC and recall >= SUPPORTED_RECALL
            else "experimental" if auc_fit >= EXPERIMENTAL_AUC
            else "unsupported"
        )
        others = m & (y == 1) & ~deepseek
        print(f"| {L} | {roc_auc_score(y[m], current[m]):.3f} | {auc_fit:.3f} | {rate(current[m & (y == 1)])} "
              f"| {rate(held[m & (y == 1)])} | {rate(current[m & (y == 0)])} | {rate(held[m & (y == 0)])} "
              f"| {rate(cross[others])} | {status[L]} |")
    print(f"| all | {roc_auc_score(y, current):.3f} | {roc_auc_score(y, held):.3f} | {rate(current[y == 1])} "
          f"| {rate(held[y == 1])} | {rate(current[y == 0])} | {rate(held[y == 0])} "
          f"| {rate(cross[(y == 1) & ~deepseek])} | |")

    theta = fit_weights(X, y, w)
    shift = offsets(theta[0] + X @ theta[1:], y, lang)
    weights = dict(zip(engines, theta[1:]))
    print("\n## Weights\n")
    print("| Engine | Weight |")
    print("|---|---|")
    for name, value in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"| {name} | {value:.3f} |")

    write_section("multilingual", {
        "intercept": round(float(theta[0]), 4),
        "weights": {ENGINE_KEYS[name]: round(float(v), 4) for name, v in weights.items()},
        "default_offset": round(float(np.median(list(shift.values()))), 4),
        "languages": {L: {"offset": round(shift[L], 4), "status": status[L]} for L in sorted(shift)},
    })


if __name__ == "__main__":
    main()
