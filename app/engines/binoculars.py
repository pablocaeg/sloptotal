import math
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


class BinocularsEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Binoculars"

    @property
    def description(self) -> str:
        return (
            "Cross-entropy ratio between two LMs — agreement signals AI-generated text"
        )

    @property
    def code(self) -> str:
        return "BN"

    @property
    def engine_type(self) -> str:
        return "statistical"

    @property
    def url(self) -> str:
        return "https://arxiv.org/abs/2401.12070"

    def analyze(self, text: str) -> EngineResult:
        try:
            from app.engines.gpt2_cache import get_gpt2_outputs, get_distil_outputs

            gpt2 = get_gpt2_outputs(text)
            distil = get_distil_outputs(text)
        except Exception as e:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details=f"Model failed: {e}",
                description=self.description,
            )

        if gpt2["loss"] is None or distil["loss"] is None:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Text too short for Binoculars analysis.",
                description=self.description,
            )

        ce_performer = gpt2["loss"]
        ce_observer = distil["loss"]

        if ce_performer < 1e-6:
            ce_performer = 1e-6

        ppl_performer = math.exp(ce_performer)
        ppl_observer = math.exp(ce_observer)
        ratio = ce_observer / ce_performer

        # GPT-2 Medium + DistilGPT-2: AI ratio ~1.05-1.15, human ~1.20-1.35+
        if ratio <= 1.08:
            ratio_score = 1.0
        elif ratio >= 1.30:
            ratio_score = 0.0
        else:
            ratio_score = 1.0 - ((ratio - 1.08) / 0.22)

        score = min(max(ratio_score, 0.0), 1.0)

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=(
                f"CE ratio: {ratio:.3f} (observer/performer), "
                f"PP performer: {ppl_performer:.1f}, PP observer: {ppl_observer:.1f}"
            ),
            description=self.description,
        )
