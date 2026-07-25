import re
import statistics
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


def _syllable_count(word: str) -> int:
    word = word.lower().rstrip("e")
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    return max(count, 1)


def _flesch_kincaid(text: str) -> float:
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip().split()) >= 3]
    if not sentences:
        return 0.0
    words = re.findall(r"[a-zA-Z]+", text)
    if not words:
        return 0.0
    total_sentences = len(sentences)
    total_words = len(words)
    total_syllables = sum(_syllable_count(w) for w in words)
    # Flesch Reading Ease
    score = (
        206.835
        - 1.015 * (total_words / total_sentences)
        - 84.6 * (total_syllables / total_words)
    )
    return score


class ReadabilityEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Readability Uniformity"

    @property
    def description(self) -> str:
        return "Checks if readability stays unnaturally consistent across paragraphs"

    @property
    def code(self) -> str:
        return "RU"

    @property
    def engine_type(self) -> str:
        return "linguistic"

    def analyze(self, text: str) -> EngineResult:
        paragraphs = [
            p.strip() for p in text.split("\n\n") if len(p.strip().split()) >= 15
        ]

        if len(paragraphs) < 3:
            # Fall back to splitting into chunks
            words = text.split()
            chunk_size = max(len(words) // 4, 20)
            paragraphs = []
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i : i + chunk_size])
                if len(chunk.split()) >= 15:
                    paragraphs.append(chunk)

        if len(paragraphs) < 3:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Text too short for readability uniformity analysis.",
                description=self.description,
            )

        fk_scores = [_flesch_kincaid(p) for p in paragraphs]
        mean_fk = statistics.mean(fk_scores)
        stdev_fk = statistics.stdev(fk_scores)
        cv = stdev_fk / abs(mean_fk) if mean_fk != 0 else 0

        # Calibrated on 108 RAID samples (72 AI, 36 human), 2026-07-25:
        #
        #              p10     median    p90
        #   AI        0.289    0.713    2.254
        #   human     0.182    0.548    1.269
        #
        # As with DivEye, both the direction and the range were wrong:
        #
        # 1. The premise -- AI keeps readability "unnaturally consistent", so a
        #    LOW CV means AI -- is not what the data shows. AI text measured a
        #    *higher* cross-paragraph Flesch CV than human text.
        # 2. The old band (0.05-0.20) sat far below both distributions, so
        #    virtually every input clamped to 0.0.
        #
        # Result was AUC 0.453, i.e. no usable signal. Separation remains weak
        # after the fix, partly because short single-paragraph inputs fall into
        # the arbitrary word-chunk fallback above, which is noisy -- hence the
        # very wide AI p90. This engine keeps a correspondingly small weight.
        CV_LOW, CV_HIGH = 0.35, 1.30
        uniformity_score = (cv - CV_LOW) / (CV_HIGH - CV_LOW)

        final_score = min(max(uniformity_score, 0.0), 1.0)

        details = (
            f"Flesch Reading Ease: mean={mean_fk:.1f}, stdev={stdev_fk:.1f}, "
            f"CV={cv:.3f} across {len(paragraphs)} paragraphs"
        )

        return EngineResult(
            engine_name=self.name,
            score=round(final_score, 3),
            verdict=score_to_engine_verdict(final_score),
            details=details,
            description=self.description,
        )
