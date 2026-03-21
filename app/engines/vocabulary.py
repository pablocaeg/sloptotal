import re
import math
from collections import Counter
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


class VocabularyEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Vocabulary Richness"

    @property
    def description(self) -> str:
        return "Measures type-token ratio, hapax legomena, and Yule's K diversity"

    @property
    def code(self) -> str:
        return "VR"

    @property
    def engine_type(self) -> str:
        return "linguistic"

    def analyze(self, text: str) -> EngineResult:
        words = re.findall(r"[a-zA-Z]+", text.lower())
        if len(words) < 20:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Text too short for vocabulary analysis.",
                description=self.description,
            )

        total = len(words)
        freq = Counter(words)
        unique = len(freq)

        # 1. Type-Token Ratio (normalize for text length using root TTR)
        root_ttr = unique / math.sqrt(total)
        # Human text: root_ttr typically 5-8+, AI tends lower (4-6)
        # Lower root_ttr → higher AI score
        ttr_score = max(0, 1.0 - ((root_ttr - 3.5) / 4.0))
        ttr_score = min(max(ttr_score, 0.0), 1.0)

        # 2. Hapax legomena ratio (words appearing exactly once)
        hapax = sum(1 for w, c in freq.items() if c == 1)
        hapax_ratio = hapax / unique if unique > 0 else 0
        # Human text: hapax ratio typically 0.5-0.7, AI text: 0.3-0.5
        hapax_score = max(0, 1.0 - ((hapax_ratio - 0.3) / 0.4))
        hapax_score = min(max(hapax_score, 0.0), 1.0)

        # 3. Yule's K (lower = richer vocabulary)
        freq_of_freq = Counter(freq.values())
        m1 = total
        m2 = sum(i * i * v for i, v in freq_of_freq.items())
        yules_k = 10000 * (m2 - m1) / (m1 * m1) if m1 > 0 else 0
        # Human text: K ~ 80-120, AI text: K ~ 120-200+
        k_score = min(max((yules_k - 80) / 120, 0.0), 1.0)

        final_score = ttr_score * 0.35 + hapax_score * 0.35 + k_score * 0.3

        details = (
            f"Root TTR: {root_ttr:.2f} (unique/√total), "
            f"Hapax ratio: {hapax_ratio:.2f} ({hapax}/{unique} words), "
            f"Yule's K: {yules_k:.1f}"
        )

        return EngineResult(
            engine_name=self.name,
            score=round(final_score, 3),
            verdict=score_to_engine_verdict(final_score),
            details=details,
            description=self.description,
        )
