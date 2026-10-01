"""The overall score: a logistic model over the engine scores, fitted on SlopBench.

calibration.json has two sections, both written by tests/eval/slopbench:
"english" (fit.py) and "multilingual" (fit_multilingual.py), the second with
an offset and a support status per language. The fits' reports, with every
number measured on data the model never saw, are in
tests/eval/slopbench/FINDINGS.md. Change them by re-running the fits, never by
hand.
"""

import json
import math
from pathlib import Path

from app.language import detect_language

_CALIBRATION = json.loads((Path(__file__).parent / "calibration.json").read_text())
SHORT_TEXT_WORDS = 80


def _logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def _weighted(section: dict, engine_scores: dict[str, float]) -> float:
    return section["intercept"] + sum(
        weight * _logit(engine_scores.get(key, 0.5))
        for key, weight in section["weights"].items()
    )


def language_support(lang: str) -> str:
    """How far detection is trusted in a language: supported, experimental or unsupported."""
    if lang == "en":
        return "supported"
    return (
        _CALIBRATION["multilingual"]["languages"]
        .get(lang, {})
        .get("status", "unsupported")
    )


def calibrated_score(
    engine_scores: dict[str, float], text: str
) -> tuple[float, str, str]:
    """0-100 score, a confidence label and the detected language.

    `engine_scores` maps engine keys (`classifier_tmr`, `perplexity`...) to
    their 0-1 scores; an engine that did not run counts as undecided (0.5).
    Short English texts are pulled toward a neutral score by
    `words / (words + k)`, in proportion to how unreliable they measured.
    Confidence is never above "low" for a short text or a language whose
    detection is not supported.
    """
    lang = detect_language(text)
    words = len(text.split())
    if lang == "en":
        english = _CALIBRATION["english"]
        z = _weighted(english, engine_scores)
        k = english["length_k"]
        reliability = words / (words + k) if k else 1.0
        z = reliability * z + (1 - reliability) * english["length_neutral"]
    else:
        multilingual = _CALIBRATION["multilingual"]
        offset = (
            multilingual["languages"]
            .get(lang, {})
            .get("offset", multilingual["default_offset"])
        )
        z = _weighted(multilingual, engine_scores) + offset
    score = 100 / (1 + math.exp(-z))

    if (
        words < SHORT_TEXT_WORDS
        or abs(z) < 1
        or language_support(lang) == "unsupported"
    ):
        confidence = "low"
    elif abs(z) < 2.5 or language_support(lang) == "experimental":
        confidence = "medium"
    else:
        confidence = "high"
    return round(score, 1), confidence, lang
