"""The quick path (/api/quick-score, /api/paragraph-score) is calibrated like the
full report: fitted on SlopBench, edges at measured human false-positive rates.
Issue #100: the old hand-weighted formula called 12.5% of human texts AI."""

import json
from pathlib import Path

import pytest

from app import calibration
from app.analyzer import quick_verdict
from app.config import QUICK_AI_MIN

BENCH = Path(__file__).parent / "eval" / "slopbench"
QUICK_ENGINES = {
    "Fakespot": "classifier_fakespot",
    "TMR Detector": "classifier_tmr",
    "BERT-tiny RAID": "classifier_bert_raid",
    "E5-Small": "classifier_e5",
    "Linguistic Markers": "linguistic",
    "Formulaic Patterns": "formulaic",
}


def test_quick_section_is_a_valid_fit():
    quick = calibration._CALIBRATION["quick"]
    assert set(quick["weights"]) == set(QUICK_ENGINES.values())
    assert all(w >= 0 for w in quick["weights"].values())
    knots = quick["band_knots"]
    assert [s for _, s in knots] == [0.0, 30.0, 45.0, 55.0, 80.0, 100.0]
    assert all(a[0] < b[0] for a, b in zip(knots, knots[1:], strict=False))


def test_undecided_engines_give_a_middling_score():
    score, confidence = calibration.quick_score({}, "word " * 200)
    assert 0 <= score <= 100
    assert confidence in {"low", "medium", "high"}


@pytest.fixture(scope="module")
def human_scores():
    texts = {}
    for path in (BENCH / "corpus").glob("human-*.jsonl"):
        for line in path.open():
            row = json.loads(line)
            texts[row["id"]] = row["text"]
    scores = {}
    for line in (BENCH / "results-20260930.jsonl").open():
        row = json.loads(line)
        if row["label"] != "human" or row["id"] not in texts:
            continue
        engines = {
            QUICK_ENGINES[k]: v for k, v in row["engines"].items() if k in QUICK_ENGINES
        }
        scores[row["id"]] = (
            row["source"],
            calibration.quick_score(engines, texts[row["id"]])[0],
        )
    return scores


def test_classic_literature_is_rarely_called_ai(human_scores):
    # 1 of 87 measured (the old formula: 11). Literature before 1920 is the
    # slice where any "ai" verdict is an error by construction.
    classics = [
        s for source, s in human_scores.values() if source == "classics-gutenberg"
    ]
    assert len(classics) == 87
    assert sum(quick_verdict(s) == "ai" for s in classics) <= 2


def test_few_human_texts_are_called_ai(human_scores):
    called = [s for _, s in human_scores.values() if s > QUICK_AI_MIN]
    assert len(called) / len(human_scores) < 0.03


# Issue #113: the behaviour documented on quick_score() -- short texts pulled
# toward neutral, confidence following the language's support -- was untested.

_LONG_SENTENCE = (
    "The committee approved the plan after several months of debate, and "
    "residents said afterwards that nobody had asked them about it. "
)
_STRONG = {key: 0.97 for key in QUICK_ENGINES.values()}


def _words(n: int) -> str:
    """The same prose at a chosen length, so only the length varies."""
    return " ".join((_LONG_SENTENCE.split() * 40)[:n])


def test_a_short_text_is_pulled_toward_the_middle():
    short_score, _ = calibration.quick_score(_STRONG, _words(20))
    long_score, _ = calibration.quick_score(_STRONG, _words(300))
    assert abs(short_score - 50) < abs(long_score - 50)


def test_a_short_text_gets_low_confidence():
    _, confidence = calibration.quick_score(_STRONG, _words(20))
    assert confidence == "low"


def test_an_unsupported_language_never_gets_more_than_low_confidence():
    # Same text as test_an_unknown_language_never_gets_more_than_low_confidence
    # in tests/test_calibration.py: long enough to clear SHORT_TEXT_WORDS, and
    # detected as "other".
    text = " ".join(
        ["Lorem ipsum dolor sit amet consectetur adipiscing elit sed eiusmod tempor."]
        * 8
    )
    assert calibration.language_support(calibration.detect_language(text)) == (
        "unsupported"
    )
    _, confidence = calibration.quick_score(_STRONG, text)
    assert confidence == "low"


@pytest.mark.parametrize("engine_score", [0.0, 1.0])
def test_the_score_stays_on_the_0_to_100_scale(engine_score):
    scores = {key: engine_score for key in QUICK_ENGINES.values()}
    score, confidence = calibration.quick_score(scores, _words(300))
    assert 0.0 <= score <= 100.0
    assert confidence in {"low", "medium", "high"}
