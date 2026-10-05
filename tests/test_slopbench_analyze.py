"""SlopBench reporting uses saved scores only, without model inference."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ANALYZE = Path(__file__).parent / "eval" / "slopbench" / "analyze.py"


def _row(words, label, score, **extra):
    return {
        "id": f"{label}-{words}-{score}",
        "words": words,
        "label": label,
        "overall": score,
        "source": "test",
        "model": "test",
        "engines": {},
        **extra,
    }


def _length_section(tmp_path, rows):
    results = tmp_path / "results.jsonl"
    results.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report = subprocess.run(
        [sys.executable, str(ANALYZE), str(results)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return report.split("### By length\n", 1)[1].split("### By generating model", 1)[0]


def _length_table(tmp_path, rows):
    section = _length_section(tmp_path, rows)
    return [line for line in section.splitlines() if line.startswith("|")][2:]


@pytest.mark.parametrize(
    ("words", "bucket"),
    [
        (0, "<100"),
        (99, "<100"),
        (100, "100-199"),
        (199, "100-199"),
        (200, "200-399"),
        (399, "200-399"),
        (400, "400+"),
        (10000, "400+"),
    ],
)
def test_length_boundaries(tmp_path, words, bucket):
    table = _length_table(tmp_path, [_row(words, "human", 45), _row(words, "ai", 46)])
    assert table == [
        f"| {label} | 0.0% (0/1) | 100.0% (1/1) | 1.000 |"
        if label == bucket
        else f"| {label} | – | – | – |"
        for label in ("<100", "100-199", "200-399", "400+")
    ]


def test_length_single_class_and_empty_buckets(tmp_path):
    assert _length_table(tmp_path, [_row(99, "human", 46), _row(100, "ai", 45)]) == [
        "| <100 | 100.0% (1/1) | – | – |",
        "| 100-199 | – | 0.0% (0/1) | – |",
        "| 200-399 | – | – | – |",
        "| 400+ | – | – | – |",
    ]


def test_length_empty_input(tmp_path):
    assert _length_table(tmp_path, []) == [
        f"| {label} | – | – | – |" for label in ("<100", "100-199", "200-399", "400+")
    ]


def test_length_uses_base_rows_and_tie_aware_auc(tmp_path):
    rows = [
        _row(100, "human", 20),
        _row(199, "human", 60),
        _row(100, "ai", 60),
        _row(199, "ai", 80),
        _row(100, "human", 100, variant="polished", base="missing"),
        _row(100, "ai", 0, variant="paraphrased", base="missing"),
        _row(100, "mixed", 100),
    ]
    assert _length_table(tmp_path, rows) == [
        "| <100 | – | – | – |",
        "| 100-199 | 50.0% (1/2) | 100.0% (2/2) | 0.875 |",
        "| 200-399 | – | – | – |",
        "| 400+ | – | – | – |",
    ]


@pytest.mark.parametrize(
    "words",
    [None, "100", True, False, -1, 1.5, 100.0, float("nan"), float("inf"), [], {}],
)
def test_length_reports_invalid_word_counts(tmp_path, words):
    section = _length_section(
        tmp_path,
        [_row(words, "human", 100), _row(100, "human", 45), _row(100, "ai", 46)],
    )
    assert (
        "Base samples omitted from this table due to missing or invalid word counts: 1."
        in section
    )
    assert "| 100-199 | 0.0% (0/1) | 100.0% (1/1) | 1.000 |" in section


def test_length_reports_missing_word_counts_without_using_cut(tmp_path):
    row = _row(50, "human", 100, cut=50)
    del row["words"]
    section = _length_section(tmp_path, [row])
    assert (
        "Base samples omitted from this table due to missing or invalid word counts: 1."
        in section
    )
    assert [line for line in section.splitlines() if line.startswith("|")][2:] == [
        f"| {label} | – | – | – |" for label in ("<100", "100-199", "200-399", "400+")
    ]
