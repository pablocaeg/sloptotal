"""Summarise a multilingual run as Markdown tables for FINDINGS.md.

Per language: how well the ensemble separates AI from human text (AUC), how
much AI it catches at the "Suspicious" band, and how often it wrongly calls
pre-AI human text "Likely AI", separately for Wikipedia and for pre-1920
literature. Then per engine: which of them still work outside English.

Usage: python analyze.py results.jsonl
"""

import json
import sys
from collections import defaultdict
from statistics import mean

from languages import LANGUAGES

SUSPICIOUS = 55
LIKELY_AI = 80


def auc(positives: list[float], negatives: list[float]) -> float | None:
    if not positives or not negatives:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}% ({part}/{whole})" if whole else "–"


def fmt(value: float | None) -> str:
    return "–" if value is None else f"{value:.3f}"


def main() -> None:
    rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
    by_lang: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_lang[row["lang"]].append(row)

    print("| Language | Human (wiki / lit) | AI (DeepSeek / older) | AUC | AI caught (≥ Suspicious) "
          "| Wikipedia called Likely AI | Literature called Likely AI | Mean score human / AI |")
    print("|---|---|---|---|---|---|---|---|")
    for lang in LANGUAGES:
        group = by_lang.get(lang, [])
        if not group:
            continue
        wiki = [r["overall"] for r in group if r["source"].startswith("wikipedia")]
        lit = [r["overall"] for r in group if r["source"].startswith("gutenberg")]
        deepseek = [r["overall"] for r in group if r["source"].startswith("ai-")]
        older = [r["overall"] for r in group if r["source"].startswith("semeval")]
        human, ai = wiki + lit, deepseek + older
        print(
            f"| {LANGUAGES[lang][0]} | {len(wiki)} / {len(lit)} | {len(deepseek)} / {len(older)} "
            f"| {fmt(auc(ai, human))} | {pct(sum(s >= SUSPICIOUS for s in ai), len(ai))} "
            f"| {pct(sum(s >= LIKELY_AI for s in wiki), len(wiki))} "
            f"| {pct(sum(s >= LIKELY_AI for s in lit), len(lit))} "
            f"| {mean(human):.1f} / {mean(ai):.1f} |"
        )

    engines = sorted({name for r in rows for name in r["engines"]})
    langs = [lang for lang in LANGUAGES if lang in by_lang]
    print("\nPer-engine AUC (AI vs pre-AI human), by language:\n")
    print("| Engine | " + " | ".join(langs) + " | mean |")
    print("|---|" + "---|" * (len(langs) + 1))
    table = []
    for engine in engines:
        values = []
        for lang in langs:
            group = by_lang[lang]
            ai = [r["engines"][engine] for r in group if r["label"] == "ai" and engine in r["engines"]]
            human = [r["engines"][engine] for r in group if r["label"] == "human" and engine in r["engines"]]
            values.append(auc(ai, human))
        known = [v for v in values if v is not None]
        table.append((mean(known) if known else 0, engine, values))
    for average, engine, values in sorted(table, reverse=True):
        print(f"| {engine} | " + " | ".join(fmt(v) for v in values) + f" | {average:.3f} |")


if __name__ == "__main__":
    main()
