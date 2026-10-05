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
HELD_OUT = Path(__file__).parent / "scores-held-out.jsonl"
L2 = 0.02
FAIRNESS_WEIGHT = 3.0
FAIRNESS_SOURCES = {
    "essay-toefl", "essay-college", "news-ccnews", "news-bbc", "news-wikinews",
    "encyclopedia-wikipedia", "classics-gutenberg",
}
TRAIN_AS_AI = {"ai-paraphrased", "ai-humanized"}
FLAGGED, CALLED_AI = 45, 55
BAND_FPR = [(30, 0.15), (45, 0.05), (55, 0.02), (80, 0.005)]
ENGINE_KEYS = {
    "TMR Detector": "classifier_tmr", "ReMoDetect": "classifier_remodetect", "Binoculars": "binoculars",
    "Fast-DetectGPT": "fast_detectgpt", "Perplexity": "perplexity", "Cross-Perplexity": "cross_perplexity",
    "Fakespot": "classifier_fakespot", "E5-Small": "classifier_e5", "BERT-tiny RAID": "classifier_bert_raid",
    "OpenAI Detector": "classifier_openai", "ChatGPT Detector": "classifier_chatgpt",
    "Desklib DeBERTa": "classifier_desklib", "SuperAnnotate": "classifier_superannotate", "GLTR": "gltr",
    "Log-Rank": "log_rank", "DivEye": "diveye", "Burstiness": "burstiness", "Linguistic Markers": "linguistic",
    "Structural Analysis": "structural", "Vocabulary Richness": "vocabulary", "Formulaic Patterns": "formulaic",
    "Readability Uniformity": "readability", "Sentiment & Hedging": "sentiment",
}


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


def z_values(theta: np.ndarray, X: np.ndarray, words: np.ndarray, k: float, neutral: float) -> np.ndarray:
    z = theta[0] + X @ theta[1:]
    r = words / (words + k) if k > 0 else np.ones_like(words)
    return r * z + (1 - r) * neutral


def scores(theta: np.ndarray, X: np.ndarray, words: np.ndarray, k: float, neutral: float) -> np.ndarray:
    return 100 / (1 + np.exp(-z_values(theta, X, words, k, neutral)))


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order]) / weights.sum()
    return float(values[order][np.searchsorted(cumulative, q)])


def band_knots(human_z: np.ndarray, human_sources: list[str]) -> list[list[float]]:
    """(z, score) knots placing each band edge where BAND_FPR of human text begins,
    every source weighted equally, so a band means a measured false-positive rate."""
    counts = {s: human_sources.count(s) for s in set(human_sources)}
    weights = np.array([1.0 / counts[s] for s in human_sources])
    edges = [(weighted_quantile(human_z, weights, 1 - fpr), score) for score, fpr in BAND_FPR]
    low, high = edges[0][0] - 6.0, edges[-1][0] + 4.0
    return [[round(low, 4), 0.0], *[[round(z, 4), float(score)] for z, score in edges], [round(high, 4), 100.0]]


def to_score(z: np.ndarray, knots: list[list[float]]) -> np.ndarray:
    xs, ys = zip(*knots)
    return np.interp(z, xs, ys)


def fit_length(theta, X, y, words, w) -> tuple[float, float]:
    """k and neutral that minimise weighted log loss on cut texts."""
    best = (0.0, 0.0, float("inf"))
    for k in [0, 5, 10, 20, 30, 40, 60, 80, 120, 200]:
        for neutral in np.linspace(-4.0, 1.0, 51):
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

    theta = fit_weights(X, y, w)
    k, neutral = 0.0, 0.0
    if cut:
        Xc, yc = matrix(cut, engines), np.array([r["y"] for r in cut], float)
        wc = sample_weights(cut)
        k, neutral = fit_length(theta, Xc, yc, np.array([r["cut"] for r in cut], float), wc)

    held_z = np.zeros(len(full))
    for source in sources:
        test = np.array([r["source"] == source for r in full])
        fold = fit_weights(X[~test], y[~test], w[~test])
        held_z[test] = z_values(fold, X[test], words[test], k, neutral)
    human_rows = [i for i, r in enumerate(full) if r["y"] == 0]
    knots = band_knots(held_z[human_rows], [full[i]["source"] for i in human_rows])
    held_out = to_score(held_z, knots)

    current = np.array([r["overall"] for r in full])
    print(f"# SlopBench calibration ({date.today().isoformat()})\n")
    print(f"{int((y == 0).sum())} human and {int((y == 1).sum())} AI texts from {len(sources)} sources; "
          f"every new-model number is leave-one-source-out.\n")
    print("Band edges, set where this share of human text (sources weighted equally) begins: "
          + ", ".join(f"{score} = top {fpr:.1%}" for score, fpr in BAND_FPR) + ".\n")
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
        sg = to_score(z_values(theta, Xg, np.array([r.get("words", 300) for r in grey], float), k, neutral), knots)
        print("\n## Grey zone (in-sample model)\n")
        print("| Variant | Samples | Median, current | Median, fitted |")
        print("|---|---|---|---|")
        by = defaultdict(list)
        for r, s in zip(grey, sg):
            by[r.get("variant") or r["label"]].append((r["overall"], s))
        for variant, pairs in sorted(by.items()):
            print(f"| {variant} | {len(pairs)} | {np.median([a for a, _ in pairs]):.1f} | {np.median([b for _, b in pairs]):.1f} |")

    if cut:
        sc = to_score(z_values(theta, matrix(cut, engines), np.array([r["cut"] for r in cut], float), k, neutral), knots)
        yc = np.array([r["y"] for r in cut])
        print(f"\n## Short texts (k = {k:.0f}, neutral = {neutral:.2f})\n")
        print("| Words | Human flagged, current | Human flagged, fitted | AI flagged, current | AI flagged, fitted |")
        print("|---|---|---|---|---|")
        for n in sorted({r["cut"] for r in cut}):
            m = np.array([r["cut"] == n for r in cut])
            cur = np.array([r["overall"] for r in cut])
            print(f"| {n} | {rate(cur[m & (yc == 0)], FLAGGED)} | {rate(sc[m & (yc == 0)], FLAGGED)} "
                  f"| {rate(cur[m & (yc == 1)], FLAGGED)} | {rate(sc[m & (yc == 1)], FLAGGED)} |")

    HELD_OUT.write_text("".join(
        json.dumps({"id": r["id"], "source": r["source"], "label": r["label"], "model": r.get("model", "human"),
                    "variant": r.get("variant", ""), "current": r["overall"], "fitted": round(float(s), 1)}) + "\n"
        for r, s in zip(full, held_out)
    ))

    weights = dict(zip(engines, theta[1:]))
    print("\n## Weights\n")
    print("| Engine | Weight |")
    print("|---|---|")
    for name, value in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"| {name} | {value:.3f} |")

    write_section("english", {
        "intercept": round(float(theta[0]), 4),
        "weights": {ENGINE_KEYS[name]: round(float(v), 4) for name, v in weights.items()},
        "length_k": k,
        "length_neutral": round(neutral, 4),
        "band_knots": knots,
    })


def write_section(name: str, section: dict) -> None:
    """Replace one section of app/calibration.json, keeping the others."""
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data["version"] = date.today().isoformat()
    data["source"] = "tests/eval/slopbench (fit.py, fit_multilingual.py)"
    data[name] = section
    OUT.write_text(json.dumps(data, indent=2) + "\n")

if __name__ == "__main__":
    main()
