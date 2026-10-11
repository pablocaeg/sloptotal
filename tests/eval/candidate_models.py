"""Score candidate Hugging Face detectors on the two evaluation corpora.

Used to decide which newer open models are worth adding as engines. Each model
runs standalone (no ensemble) with inputs truncated to 512 tokens, so numbers
are comparable across models and with the engines' own AUC columns.

    python tests/eval/candidate_models.py corpus_raid.json corpus_classics.json out.json

Reports, per model: AUC on the modern corpus (AI vs human), per-domain AUC,
mean score on pre-1920 literature (a high value there is a false positive by
construction), CPU latency per text, and parameter count.
"""

import json
import sys
import time
import random

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from app.engines.classifier_bert_raid import ClassifierBERTRaidEngine
from app.engines.classifier_e5 import ClassifierE5Engine
from app.engines.classifier_fakespot import ClassifierFakespotEngine

# (model id, how to turn logits into P(AI))
CANDIDATES = [
    ("rasbt/ai-text-detector-modernbert", "softmax1"),
    ("GeorgeDrayson/modernbert-ai-detection-raid-mage", "softmax1"),
    ("tabularisai/ai-text-detection", "softmax1"),
    ("AICodexLab/answerdotai-ModernBERT-base-ai-detector", "softmax1"),
    ("ShantanuT01/vanguard-ai-text-detector", "sigmoid"),
    ("ShantanuT01/gradient-ai-text-detector", "sigmoid"),
    ("noumenon-labs/Earlybird-fast", "softmax1"),
]

MIN_WORDS = 20
MAX_WORDS = 80
CLASSICS_COUNT = 26
EARLYBIRD_MODEL = "noumenon-labs/Earlybird-fast"

def truncate_to_word_range(text, rng):
    """Return a reproducible contiguous snippet containing 20 to 80 words."""
    words = text.split()
    if len(words) < MIN_WORDS:
        raise ValueError(f"Expected at least {MIN_WORDS} words, got {len(words)}")

    length = rng.randint(MIN_WORDS, min(MAX_WORDS, len(words)))
    start = rng.randint(0, len(words) - length)
    return " ".join(words[start : start + length])


def auc(pos, neg):
    """Mann-Whitney AUC: P(random AI text scores above random human text)."""
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg)) if pos and neg else float("nan")


def score_all(model_id, head, texts):
    tok = AutoTokenizer.from_pretrained(model_id)
    # Some checkpoints ship bfloat16 weights, which run ~50x slower on most CPUs.
    model = AutoModelForSequenceClassification.from_pretrained(model_id).float().eval()
    params = sum(p.numel() for p in model.parameters())
    out, t0 = [], time.perf_counter()
    with torch.no_grad():
        for text in texts:
            enc = tok(text, return_tensors="pt", truncation=True, max_length=512)
            logits = model(**enc).logits[0]
            if head == "sigmoid":
                out.append(torch.sigmoid(logits[0]).item())
            else:
                out.append(torch.softmax(logits, -1)[1].item())
    return out, (time.perf_counter() - t0) * 1000 / len(texts), params

def run_earlybird(snippets):
    tokenizer = AutoTokenizer.from_pretrained(EARLYBIRD_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(EARLYBIRD_MODEL)
    model = model.float().eval()

    def score(text):
        encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = model(**encoded).logits[0]
        return torch.softmax(logits, dim=-1)[1].item()

    score(snippets[0])
    started = time.perf_counter()
    scores = [score(snippet) for snippet in snippets]
    ms_per_text = (time.perf_counter() - started) * 1000 / len(snippets)
    return scores, ms_per_text


def run_baseline(engine, snippets):
    engine.analyze_batch(snippets[:1])
    started = time.perf_counter()
    scores = engine.analyze_batch(snippets)
    ms_per_text = (time.perf_counter() - started) * 1000 / len(snippets)
    return scores, ms_per_text

def score_with_different_model(texts, modern):
    modern_count = modern
    rng = random.Random(0)
    snippets = [truncate_to_word_range(row["text"], rng) for row in texts]
    models = [("Earlybird", run_earlybird(snippets))]
    for name, engine in (
        ("BERT-RAID", ClassifierBERTRaidEngine()),
        ("E5", ClassifierE5Engine()),
        ("Fakespot", ClassifierFakespotEngine()),
    ):
        models.append((name, run_baseline(engine, snippets)))
    ai_labels = [row["label"] == "ai" for row in modern]
    print(f"{'Model':<12} {'AUC':>7} {'Classics >0.5':>16} {'ms/text':>10}")
    for name, (scores, ms_per_text) in models:
        modern_scores = scores[:modern_count]
        classics_scores = scores[modern_count:]
        ai_scores = [score for score, is_ai in zip(modern_scores, ai_labels) if is_ai]
        human_scores = [score for score, is_ai in zip(modern_scores, ai_labels) if not is_ai]
        print(
            f"{name:<12} {auc(ai_scores, human_scores):>7.3f} "
            f"{sum(score > 0.5 for score in classics_scores):>7}/{CLASSICS_COUNT:<8} "
            f"{ms_per_text:>10.1f}"
        )
    
def main():
    modern = json.load(open(sys.argv[1]))
    classics = json.load(open(sys.argv[2]))
    
    if len(classics) != CLASSICS_COUNT:
            raise ValueError(f"Expected {CLASSICS_COUNT} classics, got {len(classics)}")
    texts = [r["text"] for r in modern] + [r["text"] for r in classics]
    torch.set_num_threads(6)
    score_with_different_model(texts, modern)
    
    results = {}
    for model_id, head in CANDIDATES:
        try:
            scores, ms, params = score_all(model_id, head, texts)
        except Exception as e:
            print(f"{model_id}: FAILED {e}", flush=True)
            continue
        m, c = scores[: len(modern)], scores[len(modern) :]
        ai = [s for s, r in zip(m, modern) if r["label"] == "ai"]
        hu = [s for s, r in zip(m, modern) if r["label"] == "human"]
        domains = {}
        for d in sorted({r["domain"] for r in modern}):
            da = [s for s, r in zip(m, modern) if r["domain"] == d and r["label"] == "ai"]
            dh = [s for s, r in zip(m, modern) if r["domain"] == d and r["label"] == "human"]
            domains[d] = round(auc(da, dh), 3)
        results[model_id] = {
            "auc": round(auc(ai, hu), 3),
            "domain_auc": domains,
            "human_modern_mean": round(sum(hu) / len(hu), 3),
            "ai_mean": round(sum(ai) / len(ai), 3),
            "classics_mean": round(sum(c) / len(c), 3),
            "classics_over_0_5": sum(s > 0.5 for s in c),
            "modern_human_over_0_5": sum(s > 0.5 for s in hu),
            "ms_per_text": round(ms, 1),
            "params_m": round(params / 1e6),
            "scores": {"modern": m, "classics": c},
        }
        r = results[model_id]
        print(
            f"{model_id:52} AUC {r['auc']:.3f}  classics {r['classics_mean']:.3f} "
            f"({r['classics_over_0_5']}/{len(c)} >0.5)  humanFP {r['modern_human_over_0_5']}/{len(hu)}  "
            f"{r['ms_per_text']:.0f} ms  {r['params_m']}M  {domains}",
            flush=True,
        )
    json.dump(results, open(sys.argv[3], "w"))


if __name__ == "__main__":
    main()
