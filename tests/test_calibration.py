"""The ensemble calibration is pure arithmetic over engine scores, so its
contract can be checked without running a single model."""

from app.analyzer import _calculate_full_calibrated_score, _engines
from app.calibration import _CALIBRATION, calibrated_score, language_support
from app.config import SCORE_CLEAN, SCORE_LIKELY_AI
from app.schemas import EngineResult, score_to_engine_verdict
from tests.samples import AI_TEXT, HUMAN_TEXT


def _results(score: float) -> dict[str, EngineResult]:
    return {
        key: EngineResult(
            engine_name=key,
            score=score,
            verdict=score_to_engine_verdict(score),
            details="",
        )
        for key, _ in _engines
    }


def test_the_calibration_weighs_exactly_the_registered_engines():
    registered = {key for key, _ in _engines}
    for section in ("english", "multilingual"):
        assert set(_CALIBRATION[section]["weights"]) == registered
        assert all(weight >= 0 for weight in _CALIBRATION[section]["weights"].values())


def test_unanimous_low_scores_are_clean():
    score, _ = _calculate_full_calibrated_score(_results(0.02), HUMAN_TEXT)
    assert score <= SCORE_CLEAN


def test_unanimous_high_scores_on_a_full_length_ai_text_are_flagged():
    score, confidence = _calculate_full_calibrated_score(
        _results(0.97), " ".join([AI_TEXT] * 6)
    )
    assert score > SCORE_LIKELY_AI
    assert confidence in {"high", "medium"}


def test_score_is_monotonic_in_engine_scores():
    scores = [
        _calculate_full_calibrated_score(_results(s), AI_TEXT)[0]
        for s in (0.1, 0.4, 0.7, 0.95)
    ]
    assert scores == sorted(scores)


def test_score_stays_in_range():
    for s in (0.0, 1.0):
        score, _ = _calculate_full_calibrated_score(_results(s), HUMAN_TEXT)
        assert 0.0 <= score <= 100.0


def _all(score: float) -> dict[str, float]:
    return {key: score for key, _ in _engines}


def test_a_short_text_is_pulled_toward_the_middle():
    long_score, long_confidence, _ = calibrated_score(
        _all(0.97), " ".join([AI_TEXT] * 6)
    )
    short_score, short_confidence, _ = calibrated_score(
        _all(0.97), " ".join(AI_TEXT.split()[:30])
    )

    assert short_score < long_score
    assert short_confidence == "low"
    assert long_confidence == "high"


def test_engines_that_did_not_run_count_as_undecided():
    score, _, _ = calibrated_score({}, HUMAN_TEXT)
    assert 0.0 <= score <= 100.0


def test_non_english_text_uses_the_multilingual_fit():
    spanish = " ".join(
        [
            "El ayuntamiento aprobó el plan después de varios meses de debate, y los vecinos dijeron que no se les había consultado."
        ]
        * 4
    )
    _, _, lang = calibrated_score(_all(0.5), spanish)
    assert lang == "es"
    assert language_support("es") in {"supported", "experimental", "unsupported"}


def test_an_unknown_language_never_gets_more_than_low_confidence():
    text = " ".join(
        ["Lorem ipsum dolor sit amet consectetur adipiscing elit sed eiusmod tempor."]
        * 8
    )
    _, confidence, lang = calibrated_score(_all(0.99), text)
    assert lang == "other"
    assert confidence == "low"


def test_a_short_non_english_text_is_held_back():
    sentence = "El ayuntamiento aprobó el plan después de varios meses de debate y los vecinos dijeron que no se les consultó."
    short_score, short_confidence, lang = calibrated_score(_all(0.9), sentence)
    long_score, _, _ = calibrated_score(_all(0.9), " ".join([sentence] * 10))

    assert lang == "es"
    assert short_score < long_score
    assert short_confidence == "low"


def test_a_japanese_text_is_not_held_back_as_a_one_word_text():
    paragraph = "東京都は日本の首都であり、政治や経済、文化の中心地として知られている。人口は約千四百万人で、世界でも有数の大都市圏を形成している。"
    score, _, lang = calibrated_score(_all(0.5), paragraph)

    assert lang == "ja"
    assert score > 50


def test_a_thai_text_is_not_held_back_as_a_short_text():
    paragraph = (
        "กรุงเทพมหานครเป็นเมืองหลวงและนครที่มีประชากรมากที่สุดของประเทศไทย "
        "เป็นศูนย์กลางการปกครอง การศึกษา การคมนาคมขนส่ง การเงินการธนาคาร "
        "การพาณิชย์ การสื่อสาร และความเจริญของประเทศ"
    )
    once, _, _ = calibrated_score(_all(0.5), paragraph)
    repeated, _, _ = calibrated_score(_all(0.5), " ".join([paragraph] * 6))

    assert once == repeated
