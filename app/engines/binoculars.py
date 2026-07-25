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

        # Calibrated on 108 RAID samples (72 AI spanning gpt4, chatgpt,
        # llama-chat, mistral-chat, cohere-chat and gpt3; 36 human), 2026-07-25:
        #
        #             p10     median    p90
        #   AI       1.187    1.276    1.368
        #   human    1.150    1.200    1.240
        #
        # A HIGHER observer/performer CE ratio indicates AI: the weak observer
        # (DistilGPT-2) is disproportionately worse than the strong performer
        # (GPT-2 Medium) on machine-generated text.
        #
        # The previous thresholds asserted the opposite ("AI ratio ~1.05-1.15,
        # human ~1.20-1.35") AND ramped downwards, so this engine was
        # anti-correlated with ground truth: AUC 0.160 over the corpus above. It
        # was actively pushing AI text toward "human" and human text toward
        # "AI". Ramping upward over the measured crossover gives AUC ~0.84.
        LOW, HIGH = 1.17, 1.35
        ratio_score = (ratio - LOW) / (HIGH - LOW)

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
