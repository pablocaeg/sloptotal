"""Summarise what visitors said wrote the texts they scanned.

Every report page asks "Who actually wrote this text?". The answers are stored
with the overall score and each engine's score, never the text, so they can be
used to check calibration long after the reports themselves are purged.

This prints how many answers there are, how often the verdict agreed with them,
and each engine's AUC against the "human" and "ai" answers. Treat the labels
as weak: visitors can be wrong or can answer in bad faith, so use this to find
where engines disagree with people and pick texts for careful review, not to
set weights directly.

Usage (from the repository root): python -m scripts.feedback_report [path/to/sloptotal.db]
"""

import json
import sqlite3
import sys
from collections import Counter

from app.config import DATABASE_PATH, SCORE_SUSPICIOUS


def auc(positives: list[float], negatives: list[float]) -> float | None:
    if not positives or not negatives:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else str(DATABASE_PATH)
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT * FROM report_feedback").fetchall()
    if not rows:
        print("No feedback yet.")
        return

    labels = Counter(r["label"] for r in rows)
    print(
        f"{len(rows)} answers: "
        + ", ".join(f"{k} {v}" for k, v in labels.most_common())
    )

    decided = [r for r in rows if r["label"] in ("human", "ai")]
    agree = sum(
        (r["overall_score"] >= SCORE_SUSPICIOUS) == (r["label"] == "ai")
        for r in decided
    )
    if decided:
        print(
            f"Verdict agreed with {agree} of {len(decided)} human/ai answers "
            f"({100 * agree / len(decided):.0f}%), counting Suspicious and above as AI."
        )
    overall = auc(
        [r["overall_score"] for r in decided if r["label"] == "ai"],
        [r["overall_score"] for r in decided if r["label"] == "human"],
    )
    if overall is not None:
        print(f"Ensemble AUC against visitor labels: {overall:.3f}")

    per_engine: dict[str, dict[str, list[float]]] = {}
    for r in decided:
        for engine, score in json.loads(r["engine_scores"]).items():
            per_engine.setdefault(engine, {"ai": [], "human": []})[r["label"]].append(
                score
            )
    table = [(auc(v["ai"], v["human"]), name) for name, v in per_engine.items()]
    table = sorted((a, n) for a, n in table if a is not None)
    if table:
        print("\nEngine AUC against visitor labels (lowest first):")
        for value, name in table:
            print(f"  {value:.3f}  {name}")


if __name__ == "__main__":
    main()
