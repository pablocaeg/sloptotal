#!/usr/bin/env python3
"""
Realistic Engine Benchmark — Real-world representative data
=============================================================
Tests with a diverse, balanced dataset:
- Casual human + Formal human (news, academic, professional)
- Casual AI + Formal AI (ChatGPT, Claude, various prompts)
- Real Google snippet lengths (100-250ch)
- Longer text (300-600ch) for Phase 2 URL scan simulation

Run: cd /root/sloptotal && source venv/bin/activate && python3 tests/bench_realistic.py
"""

import sys
import os
import time
import statistics
import itertools
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================================
# HUMAN TEXTS — diverse styles, representative of real Google search results
# ============================================================================

HUMAN_TEXTS = [
    # --- Casual/informal (social media, forums, personal) ---
    {
        "text": "just got back from the dentist and my mouth is completely numb lol. tried to drink coffee and it went everywhere",
        "style": "casual", "source": "social_media",
    },
    {
        "text": "PSA if you're getting the SSL cert error after updating, clear your local cert cache. Took me 2 hours to figure that out smh.",
        "style": "casual", "source": "tech_forum",
    },
    {
        "text": "honestly the new season is kinda mid. they completely butchered the storyline and the pacing feels way off compared to the books",
        "style": "casual", "source": "reddit",
    },
    {
        "text": "anyone else's cat just randomly sprint around the house at 3am? mine sounds like a tiny horse galloping through the hallway",
        "style": "casual", "source": "social_media",
    },
    {
        "text": "ngl I mass applied to like 200 jobs and only heard back from 3. the job market rn is absolutely brutal especially for new grads",
        "style": "casual", "source": "reddit",
    },

    # --- Formal human (news articles, journalism — the HARD cases for AI detection) ---
    {
        "text": "The Federal Reserve held interest rates steady on Wednesday, signaling that policymakers remain cautious about cutting borrowing costs amid persistent inflation pressures.",
        "style": "formal", "source": "news_article",
    },
    {
        "text": "Researchers at MIT have developed a new type of battery that uses aluminum and sulfur, two abundant and inexpensive materials. The technology could eventually offer a low-cost alternative to lithium-ion batteries for grid-scale energy storage.",
        "style": "formal", "source": "science_news",
    },
    {
        "text": "The company reported third-quarter revenue of $4.2 billion, beating analyst estimates by 6%. CEO Maria Sanchez attributed the strong performance to growing demand in the cloud computing division.",
        "style": "formal", "source": "business_news",
    },
    {
        "text": "Spain's coastline extends approximately 4,964 kilometers, making it one of the longest in Europe. The varied geography ranges from sandy Mediterranean beaches to rugged Atlantic cliffs along the northern coast.",
        "style": "formal", "source": "travel_article",
    },
    {
        "text": "The study, published in Nature Medicine, found that patients who received the combination therapy showed a 43% reduction in tumor size after 12 weeks compared to the control group.",
        "style": "formal", "source": "medical_news",
    },

    # --- Professional/technical human (documentation, how-tos, reviews) ---
    {
        "text": "To configure NGINX as a reverse proxy, edit the server block in your nginx.conf file. Set the proxy_pass directive to point to your upstream application server. Don't forget to include proxy_set_header for Host and X-Forwarded-For.",
        "style": "technical", "source": "documentation",
    },
    {
        "text": "I've been using this laptop for about six months now and the battery life is decent but nothing exceptional. The keyboard feels great for typing long documents. My biggest complaint is the trackpad which occasionally registers phantom clicks.",
        "style": "review", "source": "product_review",
    },
    {
        "text": "The recipe calls for soaking the chickpeas overnight, but if you're short on time you can use the quick-soak method. Bring them to a boil for one minute, then let them sit covered for an hour.",
        "style": "instructional", "source": "recipe_blog",
    },

    # --- Wikipedia/encyclopedia style (formal but factual, human-written) ---
    {
        "text": "The Great Wall of China is a series of fortifications built along the historical northern borders of China. Several walls were built from as early as the 7th century BC, with selective stretches later joined by Qin Shi Huang.",
        "style": "encyclopedia", "source": "wikipedia",
    },
    {
        "text": "Photosynthesis is the process by which green plants and certain other organisms use sunlight to synthesize nutrients from carbon dioxide and water. The process generates oxygen as a byproduct.",
        "style": "encyclopedia", "source": "educational",
    },

    # --- Long human texts (for Phase 2 URL scan simulation) ---
    {
        "text": "So I tried building my own PC for the first time and it was way harder than those YouTube videos make it look. Spent like 3 hours just trying to get the CPU cooler mounted properly. The thermal paste application was terrifying. But it actually posted on the first try which felt amazing. Now I just need to figure out why the RGB isn't working on two of the fans.",
        "style": "casual_long", "source": "reddit",
    },
    {
        "text": "The European Central Bank's latest policy meeting concluded with a decision to maintain the current interest rate at 4.25%, marking the third consecutive hold. President Christine Lagarde noted that while inflation has moderated significantly from its peak of 10.6% in October 2022, core inflation remains sticky at 2.8%, above the bank's 2% target. Markets had widely expected the decision, though several hawkish members reportedly pushed for a more restrictive stance.",
        "style": "formal_long", "source": "financial_news",
    },
    {
        "text": "I've been a barista for six years and I can tell you that oat milk is by far the hardest to steam properly. It separates if you get it too hot and the foam never holds like dairy. Almond milk is easier but honestly most people can't tell the difference between a good and bad pour with alt milks. Just don't order a bone dry cappuccino with oat milk.",
        "style": "casual_long", "source": "forum",
    },
    {
        "text": "Istanbul straddles two continents, with the Bosphorus strait separating its European and Asian sides. Founded as Byzantium around 660 BC, it later served as the capital of the Roman, Byzantine, and Ottoman empires. The historic peninsula contains landmarks including the Hagia Sophia, built in 537 AD as a cathedral, and the Blue Mosque, completed in 1616. The Grand Bazaar, one of the world's oldest covered markets, attracts over 90 million visitors annually.",
        "style": "formal_long", "source": "travel_guide",
    },
    {
        "text": "Moved to Portland three years ago and the food scene here is genuinely incredible but nobody warns you about the rain. Like I knew it rained a lot but experiencing 8 straight months of grey skies is something else entirely. Got a SAD lamp and it actually helps. The summers make up for it though, honestly June through September here is perfect weather.",
        "style": "casual_long", "source": "social_media",
    },
]

# ============================================================================
# AI-GENERATED TEXTS — various styles and models
# ============================================================================

AI_TEXTS = [
    # --- Formal/encyclopedic AI (classic ChatGPT style) ---
    {
        "text": "Climate change is one of the most pressing issues facing humanity today. Rising global temperatures are causing widespread environmental disruption across ecosystems worldwide.",
        "style": "formal", "source": "chatgpt",
    },
    {
        "text": "Machine learning has revolutionized how we approach complex problems. By leveraging large datasets, these systems identify patterns that would be impossible for humans to detect manually.",
        "style": "formal", "source": "chatgpt",
    },
    {
        "text": "Effective communication is essential in any professional setting. Active listening, empathy, and adaptability are key components of successful interpersonal interactions.",
        "style": "formal", "source": "chatgpt",
    },
    {
        "text": "The integration of artificial intelligence into healthcare has transformed diagnostic capabilities, enabling early detection of diseases through sophisticated pattern recognition algorithms.",
        "style": "formal", "source": "chatgpt",
    },
    {
        "text": "Digital transformation has become a critical imperative for organizations seeking to maintain competitive advantage in today's rapidly evolving technological landscape.",
        "style": "formal", "source": "chatgpt",
    },

    # --- AI imitating casual/personal style (the HARD cases — AI trying to sound human) ---
    {
        "text": "So I've been thinking about this a lot lately, and I honestly believe that most productivity advice is completely overrated. Like, just do the thing? Not everything needs a system or a framework.",
        "style": "casual_ai", "source": "claude",
    },
    {
        "text": "Okay hear me out, but I actually think pineapple on pizza works. The sweetness contrasts with the salty cheese and savory sauce in a way that just makes sense to me. Fight me.",
        "style": "casual_ai", "source": "chatgpt",
    },
    {
        "text": "I tried making sourdough for the first time last weekend and it was a complete disaster. The starter looked fine but the dough just wouldn't rise. Ended up with a bread-shaped brick. Back to the drawing board I guess.",
        "style": "casual_ai", "source": "claude",
    },
    {
        "text": "Hot take but remote work isn't going anywhere and companies that force return-to-office are going to lose their best talent. I've seen it happen at three different companies already.",
        "style": "casual_ai", "source": "chatgpt",
    },
    {
        "text": "Started learning guitar about three months ago and man, the calluses are real. My fingertips were so sore the first two weeks I could barely type. Getting better at barre chords now though.",
        "style": "casual_ai", "source": "claude",
    },

    # --- AI in professional/business style ---
    {
        "text": "Our quarterly results demonstrate strong execution across all business segments. Revenue growth of 15% year-over-year reflects our strategic investments in cloud infrastructure and our commitment to delivering value for our customers and shareholders.",
        "style": "business_ai", "source": "chatgpt",
    },
    {
        "text": "We are pleased to announce the launch of our new sustainability initiative, which aims to reduce our carbon footprint by 50% by 2030. This comprehensive program encompasses renewable energy adoption, supply chain optimization, and waste reduction strategies.",
        "style": "business_ai", "source": "chatgpt",
    },

    # --- AI-generated educational/informational content ---
    {
        "text": "Understanding the basics of compound interest is essential for building long-term wealth. When your investment earns interest, that interest then earns interest itself, creating an exponential growth curve over time. Starting early makes a significant difference.",
        "style": "educational_ai", "source": "chatgpt",
    },

    # --- Long AI texts (for Phase 2 simulation) ---
    {
        "text": "The rapid advancement of renewable energy technologies has fundamentally transformed the global energy landscape over the past decade. Solar photovoltaic systems have achieved remarkable cost reductions, declining by approximately 89% since 2010, making them increasingly competitive with conventional fossil fuel sources. Wind energy has similarly experienced significant technological improvements, with larger turbine designs and improved capacity factors contributing to enhanced economic viability.",
        "style": "formal_long_ai", "source": "chatgpt",
    },
    {
        "text": "In the realm of modern software engineering, the adoption of microservices architecture represents a paradigm shift from traditional monolithic application design. This architectural approach decomposes complex applications into independently deployable services, each responsible for specific business capabilities. The benefits include enhanced scalability, improved fault isolation, and the ability for development teams to work autonomously.",
        "style": "formal_long_ai", "source": "chatgpt",
    },
    {
        "text": "I've been reflecting on my experience moving to a new city last year, and honestly the hardest part wasn't finding an apartment or learning the transit system. It was building a social circle from scratch. In your twenties, friendships form naturally through school and shared experiences. But as you get older, you have to be much more intentional about putting yourself out there. I started joining local running groups and attending community events, and it made all the difference.",
        "style": "casual_long_ai", "source": "claude",
    },
    {
        "text": "The coffee industry has undergone a remarkable transformation in recent decades, evolving from a commodity-driven market to one increasingly focused on quality, sustainability, and traceability. Third-wave coffee shops now emphasize single-origin beans, precise brewing methods, and direct relationships with farmers. This shift has created new economic opportunities for producers in countries like Ethiopia, Colombia, and Guatemala.",
        "style": "formal_long_ai", "source": "chatgpt",
    },
    {
        "text": "Honestly, the whole debate about whether tabs or spaces are better for indentation misses the point entirely. What actually matters is consistency within a codebase. I've worked on projects that used both and the only time it caused real problems was when people mixed them. Just pick one and stick with it. Use your editor's auto-formatting and move on with your life.",
        "style": "casual_long_ai", "source": "chatgpt",
    },
    {
        "text": "After extensive testing of the new MacBook Pro, I can confidently say it represents a meaningful upgrade over the previous generation. The M3 Max chip delivers impressive performance gains in both single-threaded and multi-threaded workloads. Battery life has improved by approximately 20%, easily lasting a full workday of mixed use. The display remains excellent, though the notch continues to be a minor aesthetic annoyance.",
        "style": "review_ai", "source": "chatgpt",
    },
]


ENGINE_NAMES = ["bert_raid", "e5", "tmr", "fakespot"]


def load_engine(name):
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
    else:
        raise ValueError(f"Unknown engine: {name}")
    eng.analyze("warmup text for model loading")
    return eng, (time.perf_counter() - t0) * 1000


def get_scores(eng, texts):
    if hasattr(eng, 'analyze_batch'):
        return list(eng.analyze_batch(texts))
    return [eng.analyze(t).score for t in texts]


def bench_speed(eng, texts, runs=5):
    get_scores(eng, texts[:2])
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        get_scores(eng, texts)
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.mean(times), min(times), max(times)


def compute_metrics(human_scores, ai_scores, threshold=0.5):
    tp = sum(1 for s in ai_scores if s >= threshold)
    fn = sum(1 for s in ai_scores if s < threshold)
    fp = sum(1 for s in human_scores if s >= threshold)
    tn = sum(1 for s in human_scores if s < threshold)
    total = len(human_scores) + len(ai_scores)
    accuracy = (tp + tn) / total if total else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
    return {
        "accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "avg_human": statistics.mean(human_scores) if human_scores else 0,
        "avg_ai": statistics.mean(ai_scores) if ai_scores else 0,
    }


def find_best_threshold(human_scores, ai_scores):
    best_f1, best_t = 0, 0.5
    for t in [i/100 for i in range(20, 80)]:
        m = compute_metrics(human_scores, ai_scores, t)
        # Optimize for F1 but penalize false reds (score >= 0.65 on human)
        false_reds = sum(1 for s in human_scores if s >= 0.65)
        adj_f1 = m["f1"] - false_reds * 0.05
        if adj_f1 > best_f1:
            best_f1 = adj_f1
            best_t = t
    return best_t


def adaptive_score(bert, e5, tmr, fakespot, text_len):
    """Current adaptive scoring — mirrors _compute_snippet_score in analyzer.py.
    Includes formal text guard (fakespot>=0.90 AND tmr>=0.93 → cap 55%)."""

    # GUARD: Formal text unanimity detection
    # When Fakespot AND TMR both give very high scores, this is the "formal text"
    # signature seen identically on news, Wikipedia, business reports, AND AI text.
    # These engines CANNOT distinguish the two → cap to prevent false reds.
    # BERT sub-tiers: BERT sometimes correctly identifies human text when others fail.
    if fakespot >= 0.90 and tmr >= 0.93:
        if bert < 0.50:
            score = bert * 0.50 + e5 * 0.25 + fakespot * 0.15 + tmr * 0.10
            return min(score, 0.35)
        elif bert < 0.70:
            score = bert * 0.40 + e5 * 0.30 + fakespot * 0.15 + tmr * 0.15
            return min(score, 0.45)
        else:
            score = fakespot * 0.30 + e5 * 0.30 + tmr * 0.20 + bert * 0.20
            return min(score, 0.55)

    # TIER 0: Very short text (<150ch) — all engines unreliable
    if text_len < 150:
        if fakespot < 0.25:
            score = fakespot * 0.70 + e5 * 0.30
            return min(score, 0.40)
        elif fakespot < 0.50:
            score = fakespot * 0.50 + e5 * 0.25 + tmr * 0.15 + bert * 0.10
            return min(score, 0.45)
        else:
            score = fakespot * 0.40 + e5 * 0.25 + tmr * 0.15 + bert * 0.20
            return min(score, 0.50)

    # TIER 1: Fakespot confident (>=0.50) + not formal → real AI signal
    elif fakespot >= 0.50:
        if text_len >= 300:
            if e5 > 0.60:
                score = fakespot * 0.45 + e5 * 0.30 + tmr * 0.15 + bert * 0.10
            else:
                score = fakespot * 0.55 + e5 * 0.20 + tmr * 0.15 + bert * 0.10
        else:
            if fakespot >= 0.70 and e5 >= 0.70:
                score = fakespot * 0.40 + e5 * 0.30 + tmr * 0.15 + bert * 0.15
            else:
                score = fakespot * 0.40 + e5 * 0.25 + tmr * 0.15 + bert * 0.20
                score = min(score, 0.65)
        return score

    # TIER 2: Fakespot low (<0.50) + long text (300ch+) → human signal
    elif text_len >= 300:
        if fakespot >= 0.35:
            return fakespot * 0.50 + e5 * 0.25 + tmr * 0.15 + bert * 0.10
        elif e5 < 0.60:
            return fakespot * 0.40 + e5 * 0.30 + tmr * 0.15 + bert * 0.15
        else:
            return min(fakespot * 0.35 + e5 * 0.35 + tmr * 0.15 + bert * 0.15, 0.45)

    # TIER 3: Fakespot low (<0.50) + medium text (150-299ch)
    else:
        if e5 > 0.75 and tmr > 0.80:
            return min(e5 * 0.45 + tmr * 0.30 + bert * 0.10 + fakespot * 0.15, 0.55)
        elif e5 > 0.75:
            return min(e5 * 0.40 + 0.05, 0.50)
        elif e5 < 0.50:
            return e5 * 0.40 + fakespot * 0.30 + tmr * 0.15 + bert * 0.15
        else:
            return min(e5 * 0.35 + fakespot * 0.25 + tmr * 0.20 + bert * 0.20, 0.45)


def main():
    n_human = len(HUMAN_TEXTS)
    n_ai = len(AI_TEXTS)
    total = n_human + n_ai

    human_texts = [h["text"] for h in HUMAN_TEXTS]
    ai_texts = [a["text"] for a in AI_TEXTS]
    all_texts = human_texts + ai_texts

    print("=" * 110)
    print("REALISTIC ENGINE BENCHMARK — Diverse, representative test data")
    print("=" * 110)
    print(f"Human texts: {n_human} (casual={sum(1 for h in HUMAN_TEXTS if 'casual' in h['style'])}, "
          f"formal={sum(1 for h in HUMAN_TEXTS if 'formal' in h['style'])}, "
          f"technical={sum(1 for h in HUMAN_TEXTS if h['style'] in ('technical','review','instructional'))}, "
          f"encyclopedia={sum(1 for h in HUMAN_TEXTS if 'encyclopedia' in h['style'] or h['style']=='educational')})")
    print(f"AI texts:    {n_ai} (formal={sum(1 for a in AI_TEXTS if 'formal' in a['style'])}, "
          f"casual={sum(1 for a in AI_TEXTS if 'casual' in a['style'])}, "
          f"business={sum(1 for a in AI_TEXTS if 'business' in a['style'])}, "
          f"other={sum(1 for a in AI_TEXTS if a['style'] not in ['formal','casual_ai','business_ai','formal_long_ai','casual_long_ai','review_ai','educational_ai'])})")
    print(f"Char ranges: human [{min(len(t) for t in human_texts)}-{max(len(t) for t in human_texts)}], "
          f"AI [{min(len(t) for t in ai_texts)}-{max(len(t) for t in ai_texts)}]")
    print()

    # =====================================================================
    # PHASE 1: Load engines, collect scores
    # =====================================================================
    print("PHASE 1: Loading engines...")
    engines = {}
    raw = {}
    speed = {}

    for name in ENGINE_NAMES:
        print(f"  {name}...", end=" ", flush=True)
        eng, load_ms = load_engine(name)
        engines[name] = eng
        scores = get_scores(eng, all_texts)
        raw[name] = scores
        avg5, _, _ = bench_speed(eng, all_texts[:5])
        speed[name] = avg5
        print(f"loaded {load_ms:.0f}ms | 5-batch: {avg5:.0f}ms")

    # =====================================================================
    # PHASE 2: Per-text detailed scores
    # =====================================================================
    print()
    print("=" * 110)
    print("PHASE 2: PER-TEXT SCORES")
    print("=" * 110)
    print(f"  {'ID':>4} {'ch':>4} {'style':<16} {'bert':>6} {'e5':>6} {'tmr':>6} {'fs':>6}  {'src':<14}")
    print("-" * 95)

    for i, h in enumerate(HUMAN_TEXTS):
        b, e, t, f = raw["bert_raid"][i], raw["e5"][i], raw["tmr"][i], raw["fakespot"][i]
        fp_flag = ""
        if f >= 0.50:
            fp_flag = " FS-FP!"
        elif e >= 0.75 and t >= 0.80:
            fp_flag = " E5+TMR-FP"
        print(f"  H{i:02d} {len(h['text']):>4} {h['style']:<16} {b:>6.3f} {e:>6.3f} {t:>6.3f} {f:>6.3f}  {h['source']:<14}{fp_flag}")

    print()
    for i, a in enumerate(AI_TEXTS):
        idx = n_human + i
        b, e, t, f = raw["bert_raid"][idx], raw["e5"][idx], raw["tmr"][idx], raw["fakespot"][idx]
        fn_flag = ""
        if f < 0.30 and e < 0.60:
            fn_flag = " MISS?"
        print(f"  A{i:02d} {len(a['text']):>4} {a['style']:<16} {b:>6.3f} {e:>6.3f} {t:>6.3f} {f:>6.3f}  {a['source']:<14}{fn_flag}")

    # =====================================================================
    # PHASE 3: Per-engine accuracy
    # =====================================================================
    print()
    print("=" * 110)
    print("PHASE 3: PER-ENGINE ACCURACY (threshold=0.50)")
    print("=" * 110)

    # Overall
    print(f"\n--- ALL {total} texts ---")
    print(f"  {'Engine':<12} {'Acc%':>5} {'F1':>6} {'Prec':>6} {'Rec':>6} {'FP':>4} {'FN':>4} {'AvgH':>6} {'AvgA':>6} {'Gap':>6}")
    print("  " + "-" * 85)
    for name in ENGINE_NAMES:
        h_scores = raw[name][:n_human]
        a_scores = raw[name][n_human:]
        m = compute_metrics(h_scores, a_scores)
        print(f"  {name:<12} {m['accuracy']*100:>5.1f} {m['f1']:>6.3f} {m['precision']:>6.3f} {m['recall']:>6.3f} "
              f"{m['fp']:>4} {m['fn']:>4} {m['avg_human']:>6.3f} {m['avg_ai']:>6.3f} {m['avg_ai']-m['avg_human']:>6.3f}")

    # By text style — human casual vs formal
    h_casual = [i for i, h in enumerate(HUMAN_TEXTS) if "casual" in h["style"]]
    h_formal = [i for i, h in enumerate(HUMAN_TEXTS) if "formal" in h["style"] or h["style"] in ("encyclopedia", "educational")]
    h_technical = [i for i, h in enumerate(HUMAN_TEXTS) if h["style"] in ("technical", "review", "instructional")]

    a_formal = [i for i, a in enumerate(AI_TEXTS) if "formal" in a["style"]]
    a_casual = [i for i, a in enumerate(AI_TEXTS) if "casual" in a["style"]]
    a_business = [i for i, a in enumerate(AI_TEXTS) if "business" in a["style"]]

    # Short texts only (<200ch)
    h_short = [i for i, h in enumerate(HUMAN_TEXTS) if len(h["text"]) < 200]
    a_short = [i for i, a in enumerate(AI_TEXTS) if len(a["text"]) < 200]
    h_long = [i for i, h in enumerate(HUMAN_TEXTS) if len(h["text"]) >= 200]
    a_long = [i for i, a in enumerate(AI_TEXTS) if len(a["text"]) >= 200]

    subsets = [
        ("Short (<200ch)", h_short, a_short),
        ("Long (>=200ch)", h_long, a_long),
        ("Human casual", h_casual, list(range(n_ai))),
        ("Human formal", h_formal, list(range(n_ai))),
        ("Human technical", h_technical, list(range(n_ai))),
        ("AI formal vs all H", list(range(n_human)), a_formal),
        ("AI casual vs all H", list(range(n_human)), a_casual),
    ]

    for label, h_idx, a_idx in subsets:
        if not h_idx or not a_idx:
            continue
        print(f"\n--- {label} ({len(h_idx)}h + {len(a_idx)}a) ---")
        print(f"  {'Engine':<12} {'F1':>6} {'FP':>4} {'FN':>4} {'FP%':>5} {'AvgH':>6} {'AvgA':>6}")
        for name in ENGINE_NAMES:
            hs = [raw[name][i] for i in h_idx]
            asc = [raw[name][n_human + i] for i in a_idx]
            m = compute_metrics(hs, asc)
            fp_pct = m['fp'] / len(h_idx) * 100
            print(f"  {name:<12} {m['f1']:>6.3f} {m['fp']:>4} {m['fn']:>4} {fp_pct:>4.0f}% {m['avg_human']:>6.3f} {m['avg_ai']:>6.3f}")

    # =====================================================================
    # PHASE 4: All combinations with optimized weights
    # =====================================================================
    print()
    print("=" * 110)
    print("PHASE 4: ENGINE COMBINATIONS (optimized weights)")
    print("=" * 110)

    h_scores_all = {name: raw[name][:n_human] for name in ENGINE_NAMES}
    a_scores_all = {name: raw[name][n_human:] for name in ENGINE_NAMES}

    combo_results = []

    for r in range(1, len(ENGINE_NAMES) + 1):
        for combo in itertools.combinations(ENGINE_NAMES, r):
            best_f1 = 0
            best_result = None

            if len(combo) == 1:
                name = combo[0]
                hs = h_scores_all[name]
                asc = a_scores_all[name]
                bt = find_best_threshold(hs, asc)
                m = compute_metrics(hs, asc, bt)
                false_reds = sum(1 for s in hs if s >= 0.65)
                combo_results.append({
                    "engines": combo, "weights": {name: 1.0},
                    "threshold": bt,
                    "label": f"t={bt:.2f}",
                    "ms": speed[name],
                    "metrics": m, "false_reds": false_reds,
                })
                continue

            # Try many weight distributions
            step = 0.05 if len(combo) <= 3 else 0.10
            max_w = 1.0

            if len(combo) == 2:
                for w1_i in range(1, int(max_w/step)):
                    w1 = w1_i * step
                    w2 = round(1.0 - w1, 2)
                    if w2 <= 0: continue
                    weights = {combo[0]: w1, combo[1]: w2}
                    combined_h = [sum(h_scores_all[e][i] * weights[e] for e in combo) for i in range(n_human)]
                    combined_a = [sum(a_scores_all[e][i] * weights[e] for e in combo) for i in range(n_ai)]
                    bt = find_best_threshold(combined_h, combined_a)
                    m = compute_metrics(combined_h, combined_a, bt)
                    false_reds = sum(1 for s in combined_h if s >= 0.65)
                    score = m["f1"] - false_reds * 0.03
                    if score > best_f1:
                        best_f1 = score
                        best_result = {
                            "engines": combo, "weights": weights, "threshold": bt,
                            "label": "/".join(f"{weights[e]:.2f}" for e in combo) + f"(t={bt:.2f})",
                            "ms": max(speed[n] for n in combo),
                            "metrics": m, "false_reds": false_reds,
                        }

            elif len(combo) == 3:
                for w1_i in range(1, int(max_w/step)):
                    w1 = w1_i * step
                    for w2_i in range(1, int((max_w - w1)/step) + 1):
                        w2 = w2_i * step
                        w3 = round(1.0 - w1 - w2, 2)
                        if w3 <= 0: continue
                        weights = {combo[0]: w1, combo[1]: w2, combo[2]: w3}
                        combined_h = [sum(h_scores_all[e][i] * weights[e] for e in combo) for i in range(n_human)]
                        combined_a = [sum(a_scores_all[e][i] * weights[e] for e in combo) for i in range(n_ai)]
                        bt = find_best_threshold(combined_h, combined_a)
                        m = compute_metrics(combined_h, combined_a, bt)
                        false_reds = sum(1 for s in combined_h if s >= 0.65)
                        score = m["f1"] - false_reds * 0.03
                        if score > best_f1:
                            best_f1 = score
                            best_result = {
                                "engines": combo, "weights": weights, "threshold": bt,
                                "label": "/".join(f"{weights[e]:.2f}" for e in combo) + f"(t={bt:.2f})",
                                "ms": max(speed[n] for n in combo),
                                "metrics": m, "false_reds": false_reds,
                            }

            elif len(combo) == 4:
                for w1_i in range(1, 8):
                    w1 = w1_i * 0.10
                    for w2_i in range(1, int((1.0 - w1)/0.10) + 1):
                        w2 = w2_i * 0.10
                        for w3_i in range(1, int((1.0 - w1 - w2)/0.10) + 1):
                            w3 = w3_i * 0.10
                            w4 = round(1.0 - w1 - w2 - w3, 2)
                            if w4 <= 0: continue
                            weights = {combo[0]: w1, combo[1]: w2, combo[2]: w3, combo[3]: w4}
                            combined_h = [sum(h_scores_all[e][i] * weights[e] for e in combo) for i in range(n_human)]
                            combined_a = [sum(a_scores_all[e][i] * weights[e] for e in combo) for i in range(n_ai)]
                            bt = find_best_threshold(combined_h, combined_a)
                            m = compute_metrics(combined_h, combined_a, bt)
                            false_reds = sum(1 for s in combined_h if s >= 0.65)
                            score = m["f1"] - false_reds * 0.03
                            if score > best_f1:
                                best_f1 = score
                                best_result = {
                                    "engines": combo, "weights": weights, "threshold": bt,
                                    "label": "/".join(f"{weights[e]:.2f}" for e in combo) + f"(t={bt:.2f})",
                                    "ms": max(speed[n] for n in combo),
                                    "metrics": m, "false_reds": false_reds,
                                }

            if best_result:
                combo_results.append(best_result)

    combo_results.sort(key=lambda x: (-x["metrics"]["f1"], x["false_reds"], x["ms"]))

    print(f"\n{'#':>2} {'Combination':<35} {'Weights':<30} {'ms':>4} {'F1':>6} {'Prec':>6} {'FP':>3} {'FN':>3} {'FReds':>5}")
    print("-" * 105)
    for i, c in enumerate(combo_results):
        m = c["metrics"]
        name = "+".join(c["engines"])
        print(f"{i+1:>2} {name:<35} {c['label']:<30} {c['ms']:>4.0f} "
              f"{m['f1']:>6.3f} {m['precision']:>6.3f} {m['fp']:>3} {m['fn']:>3} {c['false_reds']:>5}")

    # =====================================================================
    # PHASE 5: Adaptive scoring simulation
    # =====================================================================
    print()
    print("=" * 110)
    print("PHASE 5: ADAPTIVE SCORING SIMULATION (current implementation)")
    print("=" * 110)

    print(f"\n  {'ID':>4} {'ch':>4} {'style':<16} {'score':>6} {'label':>15} {'bert':>6} {'e5':>6} {'tmr':>6} {'fs':>6}  notes")
    print("  " + "-" * 100)

    adapt_h_scores = []
    adapt_a_scores = []
    false_red_list = []

    for i, h in enumerate(HUMAN_TEXTS):
        b, e, t, f = raw["bert_raid"][i], raw["e5"][i], raw["tmr"][i], raw["fakespot"][i]
        tl = len(h["text"])
        score = adaptive_score(b, e, t, f, tl)
        adapt_h_scores.append(score)
        label = "Likely AI" if score >= 0.75 else "Maybe AI" if score >= 0.50 else "Prob Human" if score >= 0.25 else "Likely Human"
        notes = ""
        if score >= 0.65:
            notes = "FALSE RED!"
            false_red_list.append(f"H{i:02d}")
        elif score >= 0.50:
            notes = "false yellow"
        print(f"  H{i:02d} {tl:>4} {h['style']:<16} {score*100:>5.1f}% {label:>15} {b:>6.3f} {e:>6.3f} {t:>6.3f} {f:>6.3f}  {notes}")

    print()
    for i, a in enumerate(AI_TEXTS):
        idx = n_human + i
        b, e, t, f = raw["bert_raid"][idx], raw["e5"][idx], raw["tmr"][idx], raw["fakespot"][idx]
        tl = len(a["text"])
        score = adaptive_score(b, e, t, f, tl)
        adapt_a_scores.append(score)
        label = "Likely AI" if score >= 0.75 else "Maybe AI" if score >= 0.50 else "Prob Human" if score >= 0.25 else "Likely Human"
        notes = ""
        if score < 0.50:
            notes = "MISS" if score < 0.35 else "weak"
        print(f"  A{i:02d} {tl:>4} {a['style']:<16} {score*100:>5.1f}% {label:>15} {b:>6.3f} {e:>6.3f} {t:>6.3f} {f:>6.3f}  {notes}")

    # Metrics
    m = compute_metrics(adapt_h_scores, adapt_a_scores)
    print(f"\n  ADAPTIVE SCORING RESULTS:")
    print(f"  Accuracy: {m['accuracy']*100:.1f}%  F1: {m['f1']:.3f}  Precision: {m['precision']:.3f}  Recall: {m['recall']:.3f}")
    print(f"  TP: {m['tp']}  TN: {m['tn']}  FP: {m['fp']}  FN: {m['fn']}")
    print(f"  False reds: {len(false_red_list)} — {', '.join(false_red_list) if false_red_list else 'none'}")

    # Break down by style
    for style_label, indices in [("casual human", h_casual), ("formal human", h_formal),
                                  ("technical human", h_technical)]:
        if not indices:
            continue
        scores = [adapt_h_scores[i] for i in indices]
        above_50 = sum(1 for s in scores if s >= 0.50)
        above_65 = sum(1 for s in scores if s >= 0.65)
        print(f"  {style_label}: avg={statistics.mean(scores)*100:.1f}%, yellow(>=50%)={above_50}/{len(scores)}, red(>=65%)={above_65}/{len(scores)}")

    for style_label, indices in [("formal AI", a_formal), ("casual AI", a_casual)]:
        if not indices:
            continue
        scores = [adapt_a_scores[i] for i in indices]
        detected = sum(1 for s in scores if s >= 0.50)
        red = sum(1 for s in scores if s >= 0.65)
        print(f"  {style_label}: avg={statistics.mean(scores)*100:.1f}%, detected(>=50%)={detected}/{len(scores)}, red(>=65%)={red}/{len(scores)}")

    # Save data
    output = {
        "raw_scores": {k: [round(s, 4) for s in v] for k, v in raw.items()},
        "adaptive_scores": {
            "human": [round(s, 4) for s in adapt_h_scores],
            "ai": [round(s, 4) for s in adapt_a_scores],
        },
        "texts": {
            "human": [{"text": h["text"], "style": h["style"], "source": h["source"], "chars": len(h["text"])} for h in HUMAN_TEXTS],
            "ai": [{"text": a["text"], "style": a["style"], "source": a["source"], "chars": len(a["text"])} for a in AI_TEXTS],
        },
        "speed": speed,
    }
    with open("/tmp/bench_realistic_data.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Data saved to /tmp/bench_realistic_data.json")


if __name__ == "__main__":
    main()
