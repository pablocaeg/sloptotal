"""The overall score: a logistic model over the engine scores, fitted on SlopBench.

calibration.json has two sections, both written by tests/eval/slopbench:
"english" (fit.py) and "multilingual" (fit_multilingual.py), the second with
an offset and a support status per language. The fits' reports, with every
number measured on data the model never saw, are in
tests/eval/slopbench/FINDINGS.md. Change them by re-running the fits, never by
hand.
"""

import hashlib
import json
import math
from pathlib import Path

from app.language import detect_language

_HERE = Path(__file__).parent
_CALIBRATION = json.loads((_HERE / "calibration.json").read_text())
# Fingerprint of everything that turns engine scores into the overall score;
# a cached report is reused only when it was scored under the same one.
CALIBRATION_VERSION = hashlib.sha256(
    b"".join(
        (_HERE / name).read_bytes()
        for name in ("calibration.json", "calibration.py", "language.py")
    )
).hexdigest()[:16]
SHORT_TEXT_WORDS = 80
UNSPACED_LANGUAGES = {"ja", "zh"}
UNCERTAIN = (35.0, 65.0)
CONFIDENT = (15.0, 80.0)


def _logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def _weighted(section: dict, engine_scores: dict[str, float]) -> float:
    return section["intercept"] + sum(
        weight * _logit(engine_scores.get(key, 0.5))
        for key, weight in section["weights"].items()
    )


def _interpolate(z: float, knots: list[list[float]]) -> float:
    """Piecewise-linear map from the model's log-odds to the 0-100 scale, whose
    knots put each band edge where a measured share of human text begins."""
    if z <= knots[0][0]:
        return knots[0][1]
    for (z0, s0), (z1, s1) in zip(knots, knots[1:]):
        if z <= z1:
            return s0 + (s1 - s0) * (z - z0) / (z1 - z0)
    return knots[-1][1]


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
    `words / (words + k)`, in proportion to how unreliable they measured, and
    the band edges (30, 45, 55, 80) sit where a measured share of human text
    begins. Other languages written with spaces between words subtract
    `short_alpha * (1/words - 1/short_ref_words)` from the log-odds below
    `short_ref_words`. Confidence is never above "low" for a short text, a
    score in the uncertain middle, or a language whose detection is not
    supported.
    """
    lang = detect_language(text)
    words = len(text.split())
    if lang == "en":
        english = _CALIBRATION["english"]
        z = _weighted(english, engine_scores)
        k = english["length_k"]
        reliability = words / (words + k) if k else 1.0
        z = reliability * z + (1 - reliability) * english["length_neutral"]
        score = _interpolate(z, english["band_knots"])
    else:
        multilingual = _CALIBRATION["multilingual"]
        offset = (
            multilingual["languages"]
            .get(lang, {})
            .get("offset", multilingual["default_offset"])
        )
        z = _weighted(multilingual, engine_scores) + offset
        reference = multilingual["short_ref_words"]
        if lang not in UNSPACED_LANGUAGES and 0 < words < reference:
            z -= multilingual["short_alpha"] * (1 / words - 1 / reference)
        score = 100 / (1 + math.exp(-z))

    support = language_support(lang)
    if (
        words < SHORT_TEXT_WORDS
        or support == "unsupported"
        or UNCERTAIN[0] <= score <= UNCERTAIN[1]
    ):
        confidence = "low"
    elif support == "experimental" or not (
        score < CONFIDENT[0] or score >= CONFIDENT[1]
    ):
        confidence = "medium"
    else:
        confidence = "high"
    return round(score, 1), confidence, lang
