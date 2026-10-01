"""Fit the ensemble's weights on SlopBench and write app/calibration.json.

The overall score is a logistic model over the 23 engine scores:

    z = intercept + sum(weight[e] * logit(score[e]))
    z = r * z + (1 - r) * neutral,   r = words / (words + k)
    score = 100 * sigmoid(z)

Weights are non-negative, so an engine can only push a text toward "AI" when
it says AI, and every verdict can be explained engine by engine. The second
line pulls short texts toward a neutral score by as much as they are
measurably unreliable; k and neutral are fitted on the same texts cut to 50
and 100 words.

Every number reported is leave-one-source-out: the model that scores a source
never saw any text from it, human or AI, so the figures describe writing the
model has not met rather than the data it was tuned on. Human text from the
slices where detectors are known to be unfair (non-native essays, news,
encyclopedias, pre-1920 literature) is up-weighted in training.

Needs numpy and scikit-learn (offline only; production reads the JSON).
Usage: python fit.py results.jsonl [results-short.jsonl ...] > report.md
"""

import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from sklearn.metrics import roc_auc_score

OUT = Path(__file__).parents[3] / "app" / "calibration.json"
L2 = 0.02
FAIRNESS_WEIGHT = 3.0
FAIRNESS_SOURCES = {
    "essay-toefl", "essay-college", "news-ccnews", "news-bbc", "news-wikinews",
    "encyclopedia-wikipedia", "classics-gutenberg",
}
TRAIN_AS_AI = {"ai-paraphrased", "ai-humanized"}
FLAGGED, CALLED_AI = 45, 55


def logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def load(paths: list[str]) -> list[dict]:
    rows = []
    for path in paths:
        rows += [json.loads(line) for line in open(path) if line.strip()]
    return rows


def matrix(rows: list[dict], engines: list[str]) -> np.ndarray:
    return np.array([[logit(r["engines"].get(e, 0.5)) for e in engines] for r in rows])


def fit_weights(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted logistic regression, L2 on the engine weights, which are >= 0."""

    def loss(theta):
        z = theta[0] + X @ theta[1:]
        p = 1 / (1 + np.exp(-z))
        eps = 1e-9
        nll = -np.sum(w * (y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))) / w.sum()
        grad_z = w * (p - y) / w.sum()
        grad = np.concatenate([[grad_z.sum()], X.T @ grad_z])
        nll += L2 * np.sum(theta[1:] ** 2)
        grad[1:] += 2 * L2 * theta[1:]
        return nll, grad

    theta0 = np.zeros(X.shape[1] + 1)
    bounds = [(None, None)] + [(0, None)] * X.shape[1]
    return minimize(loss, theta0, jac=True, bounds=bounds, method="L-BFGS-B").x


def sample_weights(rows: list[dict]) -> np.ndarray:
    """Each source contributes equally, each class equally within it, and human
    text from the fairness slices counts FAIRNESS_WEIGHT times."""
    counts = defaultdict(int)
    for r in rows:
        counts[(r["source"], r["y"])] += 1
    weights = []
    for r in rows:
        wt = 1.0 / counts[(r["source"], r["y"])]
        if r["y"] == 0 and r["source"] in FAIRNESS_SOURCES:
            wt *= FAIRNESS_WEIGHT
        weights.append(wt)
    return np.array(weights)


def scores(theta: np.ndarray, X: np.ndarray, words: np.ndarray, k: float, neutral: float) -> np.ndarray:
    z = theta[0] + X @ theta[1:]
    r = words / (words + k) if k > 0 else np.ones_like(words)
    return 100 / (1 + np.exp(-(r * z + (1 - r) * neutral)))


def fit_length(theta, X, y, words, w) -> tuple[float, float]:
    """k and neutral that minimise weighted log loss on cut texts."""
    best = (0.0, 0.0, float("inf"))
    for k in [0, 10, 20, 30, 40, 60, 80, 120]:
        for neutral in np.linspace(-1.5, 0.5, 21):
            p = np.clip(scores(theta, X, words, k, neutral) / 100, 1e-6, 1 - 1e-6)
            ll = -np.sum(w * (y * np.log(p) + (1 - y) * np.log(1 - p))) / w.sum()
            if ll < best[2]:
                best = (float(k), float(neutral), ll)
    return best[0], best[1]


def rate(xs, cut) -> str:
    xs = list(xs)
    return f"{100 * sum(x > cut for x in xs) / len(xs):.1f}%" if xs else "–"


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
    grey = [r for r in rows if r["y"] is None]
    engines = sorted({e for r in full for e in r["engines"]})

    X, y = matrix(full, engines), np.array([r["y"] for r in full], float)
    words = np.array([r.get("words", 300) for r in full], float)
    w = sample_weights(full)
    sources = sorted({r["source"] for r in full})

    held_out = np.zeros(len(full))
    for source in sources:
        test = np.array([r["source"] == source for r in full])
        theta = fit_weights(X[~test], y[~test], w[~test])
        held_out[test] = scores(theta, X[test], words[test], 0, 0)

    theta = fit_weights(X, y, w)
    k, neutral = 0.0, 0.0
    if cut:
        Xc, yc = matrix(cut, engines), np.array([r["y"] for r in cut], float)
        wc = sample_weights(cut)
        k, neutral = fit_length(theta, Xc, yc, np.array([r["cut"] for r in cut], float), wc)

    current = np.array([r["overall"] for r in full])
    print(f"# SlopBench calibration ({date.today().isoformat()})\n")
    print(f"{int((y == 0).sum())} human and {int((y == 1).sum())} AI texts from {len(sources)} sources; "
          f"every new-model number is leave-one-source-out.\n")
    print("| | AUC | AI flagged (>45) | AI called AI (≥55) | Human flagged (>45) | Human called AI (≥55) |")
    print("|---|---|---|---|---|---|")
    for name, s in (("Current ensemble", current), ("Fitted (held out)", held_out)):
        print(f"| {name} | {roc_auc_score(y, s):.3f} | {rate(s[y == 1], FLAGGED)} | {rate(s[y == 1], CALLED_AI - 1e-9)} "
              f"| {rate(s[y == 0], FLAGGED)} | {rate(s[y == 0], CALLED_AI - 1e-9)} |")

    print("\n## By source (human flagged >45 / AI flagged >45), current → fitted\n")
    print("| Source | Human, current | Human, fitted | AI, current | AI, fitted |")
    print("|---|---|---|---|---|")
    for source in sources:
        m = np.array([r["source"] == source for r in full])
        print(f"| {source} | {rate(current[m & (y == 0)], FLAGGED)} | {rate(held_out[m & (y == 0)], FLAGGED)} "
              f"| {rate(current[m & (y == 1)], FLAGGED)} | {rate(held_out[m & (y == 1)], FLAGGED)} |")

    if grey:
        Xg = matrix(grey, engines)
        sg = scores(theta, Xg, np.array([r.get("words", 300) for r in grey], float), k, neutral)
        print("\n## Grey zone (in-sample model)\n")
        print("| Variant | Samples | Median, current | Median, fitted |")
        print("|---|---|---|---|")
        by = defaultdict(list)
        for r, s in zip(grey, sg):
            by[r.get("variant") or r["label"]].append((r["overall"], s))
        for variant, pairs in sorted(by.items()):
            print(f"| {variant} | {len(pairs)} | {np.median([a for a, _ in pairs]):.1f} | {np.median([b for _, b in pairs]):.1f} |")

    if cut:
        sc = scores(theta, matrix(cut, engines), np.array([r["cut"] for r in cut], float), k, neutral)
        yc = np.array([r["y"] for r in cut])
        print(f"\n## Short texts (k = {k:.0f}, neutral = {neutral:.2f})\n")
        print("| Words | Human flagged, current | Human flagged, fitted | AI flagged, current | AI flagged, fitted |")
        print("|---|---|---|---|---|")
        for n in sorted({r["cut"] for r in cut}):
            m = np.array([r["cut"] == n for r in cut])
            cur = np.array([r["overall"] for r in cut])
            print(f"| {n} | {rate(cur[m & (yc == 0)], FLAGGED)} | {rate(sc[m & (yc == 0)], FLAGGED)} "
                  f"| {rate(cur[m & (yc == 1)], FLAGGED)} | {rate(sc[m & (yc == 1)], FLAGGED)} |")

    weights = dict(zip(engines, theta[1:]))
    print("\n## Weights\n")
    print("| Engine | Weight |")
    print("|---|---|")
    for name, value in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"| {name} | {value:.3f} |")

    OUT.write_text(json.dumps({
        "version": date.today().isoformat(),
        "source": "tests/eval/slopbench (fit.py)",
        "intercept": round(float(theta[0]), 4),
        "weights": {name: round(float(v), 4) for name, v in weights.items()},
        "length_k": k,
        "length_neutral": round(neutral, 4),
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
