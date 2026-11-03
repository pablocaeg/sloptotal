"""Direct tests for `_confidence`, the rule that labels a score low, medium or
high. It is otherwise only reached through `calibrated_score` and `quick_score`,
where the score itself is the result of a fit, so no test pins a single branch.

Issue #112. The thresholds are imported, not copied: a re-fit that moves them
should move these tests with it.
"""

import pytest

from app.calibration import CONFIDENT, SHORT_TEXT_WORDS, UNCERTAIN, _confidence

LONG = SHORT_TEXT_WORDS
CLEAR_AI = CONFIDENT[1] + 5.0
CLEAR_HUMAN = CONFIDENT[0] - 5.0


@pytest.mark.parametrize("score", [0.0, 50.0, 99.0, 100.0])
def test_a_short_text_is_always_low(score):
    """Length wins over everything: even a 99 on a supported language."""
    assert _confidence(score, SHORT_TEXT_WORDS - 1, "supported") == "low"


@pytest.mark.parametrize("score", [CLEAR_HUMAN, 50.0, CLEAR_AI])
def test_an_unsupported_language_is_always_low(score):
    assert _confidence(score, LONG * 10, "unsupported") == "low"


@pytest.mark.parametrize(
    "score",
    [UNCERTAIN[0], (UNCERTAIN[0] + UNCERTAIN[1]) / 2, UNCERTAIN[1]],
)
def test_the_uncertain_middle_is_low_at_both_edges(score):
    assert _confidence(score, LONG * 10, "supported") == "low"


@pytest.mark.parametrize("support", ["supported", "experimental"])
def test_just_outside_the_uncertain_middle_is_not_low(support):
    """The uncertain band is inclusive, so a hair outside it is no longer low."""
    below = _confidence(UNCERTAIN[0] - 0.1, LONG * 10, support)
    above = _confidence(UNCERTAIN[1] + 0.1, LONG * 10, support)
    assert below != "low"
    assert above != "low"


@pytest.mark.parametrize("score", [CLEAR_HUMAN, CLEAR_AI])
def test_an_experimental_language_never_gets_high(score):
    assert _confidence(score, LONG * 10, "experimental") == "medium"


@pytest.mark.parametrize(
    "score",
    [CONFIDENT[0], CONFIDENT[0] + 5.0, UNCERTAIN[0] - 0.1, UNCERTAIN[1] + 0.1, 70.0],
)
def test_a_merely_leaning_score_is_medium(score):
    """Outside the uncertain middle but not past a confident edge."""
    assert _confidence(score, LONG * 10, "supported") == "medium"


@pytest.mark.parametrize("score", [0.0, CONFIDENT[0] - 0.1, CONFIDENT[1], 100.0])
def test_a_clear_score_on_a_supported_language_is_high(score):
    """Below the low edge (exclusive) or at or above the high edge (inclusive)."""
    assert _confidence(score, LONG * 10, "supported") == "high"


def test_the_word_count_boundary_is_exactly_short_text_words():
    assert _confidence(CLEAR_AI, SHORT_TEXT_WORDS - 1, "supported") == "low"
    assert _confidence(CLEAR_AI, SHORT_TEXT_WORDS, "supported") == "high"
