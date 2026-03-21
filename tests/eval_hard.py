#!/usr/bin/env python3
"""
SlopTotal HARD Accuracy Evaluation
====================================
Tests against challenging cases that expose real weaknesses:
  1. HC3 dataset (ChatGPT vs Human answers)
  2. MAGE dataset (7 LLM families, 8 domains)
  3. Hand-crafted edge cases (formal writing, short text, lightly edited AI)

Usage:
    PYTHONUNBUFFERED=1 python tests/eval_hard.py
"""

import asyncio
import random
import time
import json
import sys
from collections import defaultdict

import httpx
import numpy as np
from datasets import load_dataset

API_URL = "http://localhost:8000"
SEED = 42
CONCURRENCY = 2

random.seed(SEED)
np.random.seed(SEED)


# ─────────────────────────────────────────────────────────────
# Edge cases: formal human writing that should NOT be flagged
# ─────────────────────────────────────────────────────────────
HUMAN_EDGE_CASES = [
    {
        "text": "The relationship between socioeconomic status and educational attainment has been extensively studied in the sociological literature. Research consistently demonstrates that children from higher-income families tend to achieve better academic outcomes, though the mechanisms driving this relationship remain contested among scholars.",
        "label": 0, "model": "human", "domain": "academic", "source": "edge_case",
    },
    {
        "text": "In conclusion, the evidence presented in this paper suggests that renewable energy adoption is accelerating globally, driven by declining costs and supportive policy frameworks. However, significant challenges remain in grid integration and energy storage technology.",
        "label": 0, "model": "human", "domain": "academic", "source": "edge_case",
    },
    {
        "text": "The Supreme Court's decision in this landmark case established a precedent that would shape constitutional interpretation for decades. Writing for the majority, the Chief Justice argued that the Commerce Clause grants Congress broad authority to regulate economic activity that substantially affects interstate commerce.",
        "label": 0, "model": "human", "domain": "legal", "source": "edge_case",
    },
    {
        "text": "Patient presents with a three-day history of progressive dyspnea and productive cough with purulent sputum. Physical examination reveals bilateral crackles in the lower lung fields. Chest X-ray demonstrates bilateral infiltrates consistent with community-acquired pneumonia. Recommend empiric antibiotic therapy with azithromycin and ceftriaxone.",
        "label": 0, "model": "human", "domain": "medical", "source": "edge_case",
    },
    {
        "text": "The Board of Directors has reviewed the quarterly financial statements and notes that revenue increased by 12% year-over-year, primarily driven by expansion in the Asia-Pacific region. Operating margins improved to 18.3%, reflecting ongoing cost optimization initiatives and favorable currency effects.",
        "label": 0, "model": "human", "domain": "business", "source": "edge_case",
    },
    {
        "text": "This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware without giving effect to any choice or conflict of law provision or rule. Any legal suit, action, or proceeding arising out of or related to this Agreement shall be instituted exclusively in the federal or state courts located in New Castle County, Delaware.",
        "label": 0, "model": "human", "domain": "legal", "source": "edge_case",
    },
    {
        "text": "The mitochondrial electron transport chain consists of four major protein complexes embedded in the inner mitochondrial membrane. Complex I accepts electrons from NADH and transfers them to ubiquinone, while simultaneously pumping protons across the membrane to generate the electrochemical gradient used by ATP synthase.",
        "label": 0, "model": "human", "domain": "textbook", "source": "edge_case",
    },
    {
        "text": "According to our analysis, the proposed infrastructure project will require an estimated investment of $4.2 billion over the next five years. The cost-benefit analysis indicates a net present value of $1.8 billion, assuming a discount rate of 7% and a project lifetime of 30 years.",
        "label": 0, "model": "human", "domain": "report", "source": "edge_case",
    },
    {
        "text": "We investigated the optical properties of quantum dots synthesized using a modified hot-injection method. Transmission electron microscopy revealed uniform particle sizes with a mean diameter of 4.2 nm and a standard deviation of 0.3 nm. The photoluminescence spectra exhibited a narrow emission peak at 620 nm with a full width at half maximum of 28 nm.",
        "label": 0, "model": "human", "domain": "academic", "source": "edge_case",
    },
    {
        "text": "The recipe calls for two cups of all-purpose flour, one teaspoon of baking soda, half a teaspoon of salt, and three-quarters of a cup of unsalted butter at room temperature. Cream the butter and sugar together until light and fluffy, approximately three to four minutes with an electric mixer on medium speed.",
        "label": 0, "model": "human", "domain": "recipe", "source": "edge_case",
    },
]

# ─────────────────────────────────────────────────────────────
# Edge cases: AI text that's been lightly human-edited
# ─────────────────────────────────────────────────────────────
AI_EDGE_CASES = [
    {
        "text": "Climate change is one of the most pressing issues facing humanity today. Rising global temperatures, driven primarily by the burning of fossil fuels, are causing widespread environmental disruption. From melting ice caps to increasingly severe weather events, the impacts are being felt across every continent. Addressing this challenge requires coordinated international action and a fundamental shift in how we produce and consume energy.",
        "label": 1, "model": "chatgpt_style", "domain": "essay", "source": "edge_case",
    },
    {
        "text": "Machine learning has revolutionized the way we approach complex problems in computer science and beyond. By leveraging large datasets and sophisticated algorithms, these systems can identify patterns and make predictions that would be impossible for humans to achieve manually. From natural language processing to computer vision, the applications of machine learning continue to expand at a remarkable pace.",
        "label": 1, "model": "chatgpt_style", "domain": "tech", "source": "edge_case",
    },
    {
        "text": "The French Revolution of 1789 marked a pivotal turning point in European history. Fueled by widespread discontent with the monarchy, economic hardship, and Enlightenment ideals, the revolution fundamentally transformed French society and governance. The Declaration of the Rights of Man and of the Citizen established principles of liberty, equality, and fraternity that would influence democratic movements worldwide.",
        "label": 1, "model": "chatgpt_style", "domain": "history", "source": "edge_case",
    },
    {
        "text": "Effective communication is essential in any professional setting. Whether you're presenting to stakeholders, writing an email to colleagues, or participating in a team meeting, the ability to convey your ideas clearly and persuasively can significantly impact your career trajectory. Active listening, empathy, and adaptability are key components of successful communication.",
        "label": 1, "model": "chatgpt_style", "domain": "business", "source": "edge_case",
    },
    {
        "text": "Quantum computing represents a paradigm shift in computational power. Unlike classical computers that use bits representing 0 or 1, quantum computers utilize qubits that can exist in superposition states. This enables quantum computers to process certain types of calculations exponentially faster than their classical counterparts, with potential applications in cryptography, drug discovery, and optimization problems.",
        "label": 1, "model": "chatgpt_style", "domain": "tech", "source": "edge_case",
    },
]


# ─────────────────────────────────────────────────────────────
# Short text edge cases (tweets, comments, etc.)
# ─────────────────────────────────────────────────────────────
SHORT_HUMAN = [
    {"text": "just got back from the dentist and my mouth is completely numb. tried to drink coffee and it dribbled all down my shirt lmao", "label": 0, "model": "human", "domain": "social", "source": "short"},
    {"text": "honestly the new season is kinda mid. they completely butchered the storyline from the books and the pacing feels off", "label": 0, "model": "human", "domain": "social", "source": "short"},
    {"text": "PSA: if you're running into the SSL certificate error after the update, you need to clear your local cert cache. Took me 2 hours to figure that out.", "label": 0, "model": "human", "domain": "tech_comment", "source": "short"},
    {"text": "My grandmother used to make this exact dish every Sunday. The secret is to use real saffron, not the powdered stuff they sell at supermarkets.", "label": 0, "model": "human", "domain": "social", "source": "short"},
    {"text": "Unpopular opinion but I think the original is way better than the remaster. They changed the color grading and it looks completely different", "label": 0, "model": "human", "domain": "social", "source": "short"},
]

SHORT_AI = [
    {"text": "Here are five tips for improving your productivity: First, prioritize your tasks using the Eisenhower Matrix. Second, eliminate distractions by silencing notifications. Third, use the Pomodoro Technique.", "label": 1, "model": "chatgpt_style", "domain": "advice", "source": "short"},
    {"text": "This is a great question! The main difference between machine learning and deep learning is that deep learning uses neural networks with multiple layers, while traditional machine learning relies on simpler algorithms.", "label": 1, "model": "chatgpt_style", "domain": "qa", "source": "short"},
    {"text": "I hope this helps! Let me know if you have any other questions. In summary, the key takeaway is that consistent practice and deliberate effort are essential for mastering any new skill.", "label": 1, "model": "chatgpt_style", "domain": "qa", "source": "short"},
]


# ─────────────────────────────────────────────────────────────
# Load HC3 dataset
# ─────────────────────────────────────────────────────────────

def load_hc3_samples(n_per_class: int = 100) -> list[dict]:
    """Load HC3: Human vs ChatGPT answers."""
    print("Loading HC3 dataset (Hello-SimpleAI/HC3, all split)...")
    try:
        ds = load_dataset("Hello-SimpleAI/HC3", "all", split="train", trust_remote_code=True)
    except Exception as e:
        print(f"  Failed to load HC3: {e}")
        print("  Trying alternate config...")
        try:
            ds = load_dataset("Hello-SimpleAI/HC3", split="train", trust_remote_code=True)
        except Exception as e2:
            print(f"  Also failed: {e2}")
            return []

    human_samples = []
    ai_samples = []

    for row in ds:
        human_answers = row.get("human_answers", [])
        chatgpt_answers = row.get("chatgpt_answers", [])

        for ans in human_answers:
            if len(ans) >= 60:
                text = ans[:2000]
                human_samples.append({
                    "text": text, "label": 0, "model": "human",
                    "domain": "hc3_qa", "source": "hc3",
                })

        for ans in chatgpt_answers:
            if len(ans) >= 60:
                text = ans[:2000]
                ai_samples.append({
                    "text": text, "label": 1, "model": "chatgpt",
                    "domain": "hc3_qa", "source": "hc3",
                })

        if len(human_samples) >= n_per_class * 3 and len(ai_samples) >= n_per_class * 3:
            break

    print(f"  Human pool: {len(human_samples)}, ChatGPT pool: {len(ai_samples)}")

    h = random.sample(human_samples, min(n_per_class, len(human_samples)))
    a = random.sample(ai_samples, min(n_per_class, len(ai_samples)))

    print(f"  Selected: {len(h)} human + {len(a)} ChatGPT")
    return h + a


# ─────────────────────────────────────────────────────────────
# Load MAGE dataset
# ─────────────────────────────────────────────────────────────

def load_mage_samples(n_per_class: int = 100) -> list[dict]:
    """Load MAGE: Machine-generated text in the wild."""
    print("Loading MAGE dataset (yaful/MAGE)...")
    try:
        ds = load_dataset("yaful/MAGE", split="train", streaming=True, trust_remote_code=True)
    except Exception as e:
        print(f"  Failed to load MAGE: {e}")
        return []

    human_samples = []
    ai_samples = []
    ai_by_domain = defaultdict(int)

    seen = 0
    for row in ds:
        text = row.get("text", "")
        label = row.get("label", -1)
        domain = row.get("domain", "unknown")

        if len(text) < 60:
            continue

        text = text[:2000]
        seen += 1

        if label == 0:  # human
            if len(human_samples) < n_per_class * 3:
                human_samples.append({
                    "text": text, "label": 0, "model": "human",
                    "domain": f"mage_{domain}", "source": "mage",
                })
        elif label == 1:  # AI
            if len(ai_samples) < n_per_class * 3:
                ai_samples.append({
                    "text": text, "label": 1, "model": "mage_ai",
                    "domain": f"mage_{domain}", "source": "mage",
                })
                ai_by_domain[domain] += 1

        if len(human_samples) >= n_per_class * 3 and len(ai_samples) >= n_per_class * 3:
            break

        if seen % 5000 == 0:
            print(f"  Scanned {seen}: {len(human_samples)} human, {len(ai_samples)} AI")

    print(f"  Scanned {seen} total: {len(human_samples)} human, {len(ai_samples)} AI")
    print(f"  AI domains: {dict(ai_by_domain)}")

    h = random.sample(human_samples, min(n_per_class, len(human_samples)))
    a = random.sample(ai_samples, min(n_per_class, len(ai_samples)))

    print(f"  Selected: {len(h)} human + {len(a)} AI")
    return h + a


# ─────────────────────────────────────────────────────────────
# API client
# ─────────────────────────────────────────────────────────────

async def run_quick_score(client: httpx.AsyncClient, text: str) -> dict:
    try:
        resp = await client.post(
            f"{API_URL}/api/quick-score",
            json={"text": text},
            timeout=30.0,
        )
        if resp.status_code == 429:
            await asyncio.sleep(2)
            resp = await client.post(f"{API_URL}/api/quick-score", json={"text": text}, timeout=30.0)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}", "score": 50.0, "verdict": "error", "engines": [], "confidence": "error"}
    except Exception as e:
        return {"error": str(e), "score": 50.0, "verdict": "error", "engines": [], "confidence": "error"}


async def run_full_analyze(client: httpx.AsyncClient, text: str) -> dict:
    """Run the full 23-engine pipeline via /api/analyze."""
    try:
        resp = await client.post(
            f"{API_URL}/api/analyze",
            json={"text": text},
            timeout=120.0,
        )
        if resp.status_code == 429:
            await asyncio.sleep(5)
            resp = await client.post(f"{API_URL}/api/analyze", json={"text": text}, timeout=120.0)
        if resp.status_code == 200:
            data = resp.json()
            # Normalize to match quick-score response format
            score = data.get("overall_score", 50.0)
            if score <= 35:
                verdict = "clean"
            elif score <= 65:
                verdict = "mixed"
            else:
                verdict = "ai"
            # Extract per-engine scores
            engines = []
            for er in data.get("engine_results", []):
                engines.append({
                    "engine": er.get("engine_key", er.get("engine_name", "")),
                    "score": round(er.get("score", 0) * 100, 1),
                    "verdict": er.get("verdict", ""),
                })
            return {"score": score, "verdict": verdict, "confidence": "n/a", "engines": engines}
        return {"error": f"HTTP {resp.status_code}", "score": 50.0, "verdict": "error", "engines": [], "confidence": "error"}
    except Exception as e:
        return {"error": str(e), "score": 50.0, "verdict": "error", "engines": [], "confidence": "error"}


async def evaluate_samples(samples: list[dict], label: str, mode: str = "quick") -> list[dict]:
    print(f"\n{'='*60}")
    print(f"EVALUATING: {label} ({len(samples)} samples) [mode={mode}]")
    print(f"{'='*60}")

    if not samples:
        print("  No samples to evaluate!")
        return []

    results = []
    concurrency = CONCURRENCY if mode == "quick" else 1  # Full pipeline is heavy
    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    errors = 0
    start = time.perf_counter()

    async def process(sample):
        nonlocal completed, errors
        async with semaphore:
            if mode == "full":
                resp = await run_full_analyze(client, sample["text"])
            else:
                resp = await run_quick_score(client, sample["text"])
            completed += 1
            if "error" in resp and resp.get("verdict") == "error":
                errors += 1
            if completed % 25 == 0 or completed == len(samples):
                elapsed = time.perf_counter() - start
                rate = completed / elapsed
                eta = (len(samples) - completed) / rate if rate > 0 else 0
                print(f"  [{completed}/{len(samples)}] {rate:.1f}/s ETA {eta:.0f}s errors={errors}")
            return {**sample, "response": resp}

    async with httpx.AsyncClient() as client:
        tasks = [process(s) for s in samples]
        results = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - start
    print(f"  Done: {len(results)} in {elapsed:.1f}s ({errors} errors)")
    return [r for r in results if r["response"].get("verdict") != "error"]


# ─────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────

def analyze_results(results: list[dict], section_name: str, thresholds=None):
    """Full metrics analysis for a result set."""
    if not results:
        print(f"\n  [{section_name}] No results to analyze.")
        return {}

    scores = np.array([r["response"]["score"] / 100.0 for r in results])
    labels = np.array([r["label"] for r in results])
    n_human = (labels == 0).sum()
    n_ai = (labels == 1).sum()

    print(f"\n{'─'*60}")
    print(f"  {section_name}")
    print(f"  Samples: {len(results)} ({n_ai} AI + {n_human} human)")
    print(f"{'─'*60}")

    # Score distributions
    human_scores = scores[labels == 0] * 100
    ai_scores = scores[labels == 1] * 100
    print(f"\n  Score distributions:")
    print(f"    Human: mean={human_scores.mean():.1f}, median={np.median(human_scores):.1f}, std={human_scores.std():.1f}, range=[{human_scores.min():.1f}, {human_scores.max():.1f}]")
    if len(ai_scores) > 0:
        print(f"    AI:    mean={ai_scores.mean():.1f}, median={np.median(ai_scores):.1f}, std={ai_scores.std():.1f}, range=[{ai_scores.min():.1f}, {ai_scores.max():.1f}]")

    # Threshold sweep
    if thresholds is None:
        thresholds = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]

    print(f"\n  {'Thresh':>7} {'Acc':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'FPR':>6} {'FNR':>6}")
    print(f"  {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")

    best_f1 = 0
    best_t = 0.5

    for t in thresholds:
        pred = (scores > t).astype(int)
        tp = ((pred == 1) & (labels == 1)).sum()
        fp = ((pred == 1) & (labels == 0)).sum()
        fn = ((pred == 0) & (labels == 1)).sum()
        tn = ((pred == 0) & (labels == 0)).sum()

        acc = (tp + tn) / len(labels)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0

        marker = ""
        if f1 > best_f1:
            best_f1 = f1
            best_t = t
            marker = " *"

        print(f"  {t:>6.0%}  {acc:>5.1%} {prec:>5.1%} {rec:>5.1%} {f1:>5.3f} {fpr:>5.1%} {fnr:>5.1%}{marker}")

    print(f"\n  Best F1: {best_f1:.3f} at threshold {best_t:.0%}")

    # Per-engine analysis
    engine_scores = defaultdict(lambda: {"human": [], "ai": []})
    for r in results:
        for eng in r["response"].get("engines", []):
            name = eng.get("engine", "?")
            s = eng["score"] / 100.0
            key = "ai" if r["label"] == 1 else "human"
            engine_scores[name][key].append(s)

    if engine_scores:
        print(f"\n  Per-engine score means:")
        print(f"  {'Engine':<25} {'Human':>7} {'AI':>7} {'Gap':>7}")
        print(f"  {'-'*25} {'-'*7} {'-'*7} {'-'*7}")
        for eng in sorted(engine_scores.keys()):
            h_mean = np.mean(engine_scores[eng]["human"]) if engine_scores[eng]["human"] else 0
            a_mean = np.mean(engine_scores[eng]["ai"]) if engine_scores[eng]["ai"] else 0
            gap = a_mean - h_mean
            print(f"  {eng:<25} {h_mean:>6.1%} {a_mean:>6.1%} {gap:>+6.1%}")

    # Per-model breakdown
    models = defaultdict(lambda: {"scores": [], "labels": []})
    for r in results:
        m = r["model"]
        models[m]["scores"].append(r["response"]["score"] / 100.0)
        models[m]["labels"].append(r["label"])

    if len(models) > 1:
        print(f"\n  Per-model breakdown (threshold={best_t:.0%}):")
        print(f"  {'Model':<20} {'N':>4} {'Mean':>7} {'Det/Rej':>7}")
        print(f"  {'-'*20} {'-'*4} {'-'*7} {'-'*7}")
        for m in sorted(models.keys()):
            s = np.array(models[m]["scores"])
            l = np.array(models[m]["labels"])
            mean = s.mean()
            if l[0] == 1:  # AI
                rate = (s > best_t).mean()
                print(f"  {m:<20} {len(s):>4} {mean:>6.1%} {rate:>6.1%} det")
            else:
                rate = (s <= best_t).mean()
                print(f"  {m:<20} {len(s):>4} {mean:>6.1%} {rate:>6.1%} rej")

    # Calibration
    print(f"\n  Calibration:")
    print(f"  {'Bucket':>12} {'Count':>5} {'Actual AI%':>10}")
    print(f"  {'-'*12} {'-'*5} {'-'*10}")
    for lo, hi in [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]:
        mask = (scores >= lo) & (scores < hi)
        if mask.sum() == 0:
            continue
        actual = labels[mask].mean()
        print(f"  {lo:.0%}-{hi:.0%}     {mask.sum():>5} {actual:>9.1%}")

    # Confidence analysis
    by_conf = defaultdict(lambda: {"correct": 0, "total": 0})
    for r in results:
        conf = r["response"].get("confidence", "unknown")
        is_correct = (r["response"]["score"] / 100.0 > best_t) == (r["label"] == 1)
        by_conf[conf]["total"] += 1
        by_conf[conf]["correct"] += int(is_correct)

    print(f"\n  Confidence level accuracy:")
    for conf in ["high", "medium", "low", "unknown"]:
        if by_conf[conf]["total"]:
            acc = by_conf[conf]["correct"] / by_conf[conf]["total"]
            print(f"    {conf:<10} {by_conf[conf]['total']:>4} samples, {acc:.1%} accurate")

    return {
        "n": len(results),
        "best_f1": round(best_f1, 4),
        "best_threshold": best_t,
        "human_mean_score": round(float(human_scores.mean()), 1),
        "ai_mean_score": round(float(ai_scores.mean()), 1) if len(ai_scores) > 0 else None,
    }


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

async def main():
    # Check server
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{API_URL}/health", timeout=5.0)
            health = resp.json()
            print(f"Server: {health['status']} ({health['engines']} engines)")
        except Exception as e:
            print(f"Server not reachable: {e}")
            sys.exit(1)

    all_metrics = {}

    # ─── 1. HC3 (ChatGPT vs Human) ───
    hc3_samples = load_hc3_samples(100)
    if hc3_samples:
        hc3_results = await evaluate_samples(hc3_samples, "HC3 (ChatGPT vs Human)")
        all_metrics["hc3"] = analyze_results(hc3_results, "HC3: ChatGPT vs Human Q&A")

    # ─── 2. MAGE (Multi-domain, multi-model) ───
    mage_samples = load_mage_samples(100)
    if mage_samples:
        mage_results = await evaluate_samples(mage_samples, "MAGE (multi-domain)")
        all_metrics["mage"] = analyze_results(mage_results, "MAGE: Multi-Domain Multi-Model")

    # ─── 3. Edge cases: Formal human writing ───
    edge_human = HUMAN_EDGE_CASES
    edge_ai = AI_EDGE_CASES
    edge_short = SHORT_HUMAN + SHORT_AI
    edge_all = edge_human + edge_ai + edge_short
    random.shuffle(edge_all)

    edge_results = await evaluate_samples(edge_all, "Edge Cases")
    all_metrics["edge_cases"] = analyze_results(edge_results, "Edge Cases (Formal + Short + Edited AI)")

    # Breakdown edge cases by source type
    formal_human_results = [r for r in edge_results if r["source"] == "edge_case" and r["label"] == 0]
    chatgpt_style_results = [r for r in edge_results if r["source"] == "edge_case" and r["label"] == 1]
    short_results = [r for r in edge_results if r["source"] == "short"]

    if formal_human_results:
        print(f"\n  === Formal Human Writing (should NOT be flagged) ===")
        for r in formal_human_results:
            score = r["response"]["score"]
            verdict = r["response"]["verdict"]
            conf = r["response"].get("confidence", "?")
            domain = r["domain"]
            flag = " *** FALSE POSITIVE ***" if score > 50 else ""
            print(f"    {domain:<12} score={score:>5.1f} verdict={verdict:<6} conf={conf}{flag}")

    if chatgpt_style_results:
        print(f"\n  === ChatGPT-style AI Text (should BE flagged) ===")
        for r in chatgpt_style_results:
            score = r["response"]["score"]
            verdict = r["response"]["verdict"]
            conf = r["response"].get("confidence", "?")
            domain = r["domain"]
            flag = " *** MISSED ***" if score <= 50 else ""
            print(f"    {domain:<12} score={score:>5.1f} verdict={verdict:<6} conf={conf}{flag}")

    if short_results:
        print(f"\n  === Short Texts ===")
        for r in short_results:
            score = r["response"]["score"]
            verdict = r["response"]["verdict"]
            correct = (score > 50) == (r["label"] == 1)
            status = "OK" if correct else "WRONG"
            label_str = "AI" if r["label"] == 1 else "Human"
            print(f"    [{label_str:<5}] score={score:>5.1f} verdict={verdict:<6} {status}")

    # ─── Combined summary ───
    all_results = []
    if hc3_samples:
        all_results.extend(hc3_results)
    if mage_samples:
        all_results.extend(mage_results)
    all_results.extend(edge_results)

    if all_results:
        print(f"\n\n{'='*60}")
        print(f"COMBINED RESULTS (ALL DATASETS)")
        print(f"{'='*60}")
        all_metrics["combined"] = analyze_results(all_results, "All Datasets Combined")

    # Save
    with open("tests/eval_hard_results.json", "w") as f:
        json.dump(all_metrics, f, indent=2, default=str)
    print(f"\nResults saved to tests/eval_hard_results.json")

    # Final summary
    print(f"\n\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    for name, m in all_metrics.items():
        if m:
            print(f"  {name:<20} F1={m.get('best_f1', 0):.3f} @ {m.get('best_threshold', 0):.0%}  |  Human avg={m.get('human_mean_score', '?')}  AI avg={m.get('ai_mean_score', '?')}")

    # ─── Full pipeline eval (if requested) ───
    if "--full" in sys.argv:
        print(f"\n\n{'#'*60}")
        print(f"FULL 23-ENGINE PIPELINE EVALUATION")
        print(f"{'#'*60}")

        full_metrics = {}

        if mage_samples:
            mage_full_results = await evaluate_samples(mage_samples, "MAGE (full pipeline)", mode="full")
            full_metrics["mage_full"] = analyze_results(mage_full_results, "MAGE: Full 23-Engine Pipeline")

        edge_full_results = await evaluate_samples(edge_all, "Edge Cases (full pipeline)", mode="full")
        full_metrics["edge_full"] = analyze_results(edge_full_results, "Edge Cases: Full 23-Engine Pipeline")

        # Edge case breakdown for full pipeline
        formal_full = [r for r in edge_full_results if r["source"] == "edge_case" and r["label"] == 0]
        chatgpt_full = [r for r in edge_full_results if r["source"] == "edge_case" and r["label"] == 1]
        short_full = [r for r in edge_full_results if r["source"] == "short"]

        if formal_full:
            print(f"\n  === Formal Human Writing (FULL) ===")
            for r in formal_full:
                score = r["response"]["score"]
                verdict = r["response"]["verdict"]
                domain = r["domain"]
                flag = " *** FALSE POSITIVE ***" if score > 50 else ""
                print(f"    {domain:<12} score={score:>5.1f} verdict={verdict:<6}{flag}")

        if chatgpt_full:
            print(f"\n  === ChatGPT-style AI Text (FULL) ===")
            for r in chatgpt_full:
                score = r["response"]["score"]
                verdict = r["response"]["verdict"]
                domain = r["domain"]
                flag = " *** MISSED ***" if score <= 50 else ""
                print(f"    {domain:<12} score={score:>5.1f} verdict={verdict:<6}{flag}")

        if short_full:
            print(f"\n  === Short Texts (FULL) ===")
            for r in short_full:
                score = r["response"]["score"]
                verdict = r["response"]["verdict"]
                correct = (score > 50) == (r["label"] == 1)
                status = "OK" if correct else "WRONG"
                label_str = "AI" if r["label"] == 1 else "Human"
                print(f"    [{label_str:<5}] score={score:>5.1f} verdict={verdict:<6} {status}")

        # Combined full
        all_full = []
        if mage_samples:
            all_full.extend(mage_full_results)
        all_full.extend(edge_full_results)
        if all_full:
            full_metrics["combined_full"] = analyze_results(all_full, "All Datasets: Full Pipeline Combined")

        with open("tests/eval_hard_full_results.json", "w") as f:
            json.dump(full_metrics, f, indent=2, default=str)

        print(f"\n\n{'='*60}")
        print("FULL PIPELINE SUMMARY")
        print(f"{'='*60}")
        for name, m in full_metrics.items():
            if m:
                print(f"  {name:<20} F1={m.get('best_f1', 0):.3f} @ {m.get('best_threshold', 0):.0%}  |  Human avg={m.get('human_mean_score', '?')}  AI avg={m.get('ai_mean_score', '?')}")


if __name__ == "__main__":
    asyncio.run(main())
