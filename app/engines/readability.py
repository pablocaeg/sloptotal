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

        # Low variance in readability = AI-like
        # AI text CV typically 0.02-0.10, human text 0.10-0.40+
        # Use stricter threshold to avoid flagging consistent human writing
        if cv <= 0.05:
            uniformity_score = 1.0
        elif cv >= 0.20:
            uniformity_score = 0.0
        else:
            uniformity_score = 1.0 - ((cv - 0.05) / 0.15)

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
