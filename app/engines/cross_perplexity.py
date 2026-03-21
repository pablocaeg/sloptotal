import math
import threading
import torch
from transformers import GPT2LMHeadModel, GPT2TokenizerFast
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

# DistilGPT-2 as a second, smaller model
_distil_model = None
_distil_tokenizer = None
_distil_lock = threading.Lock()


def _load_distil_model():
    global _distil_model, _distil_tokenizer
    if _distil_model is None:
        _distil_tokenizer = GPT2TokenizerFast.from_pretrained("distilgpt2")
        _distil_model = GPT2LMHeadModel.from_pretrained("distilgpt2")
        _distil_model.eval()
    return _distil_model, _distil_tokenizer


class CrossPerplexityEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Cross-Perplexity"

    @property
    def description(self) -> str:
        return "Compares perplexity across GPT-2 Large and DistilGPT-2 — agreement amplifies signal"

    @property
    def code(self) -> str:
        return "XP"

    @property
    def engine_type(self) -> str:
        return "statistical"

    @property
    def url(self) -> str:
        return "https://huggingface.co/distilbert/distilgpt2"

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
                details=f"Model loading failed: {e}",
                description=self.description,
            )

        if gpt2["loss"] is None or distil["loss"] is None:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Text too short for cross-perplexity analysis.",
                description=self.description,
            )

        pp_medium = math.exp(gpt2["loss"])
        pp_distil = math.exp(distil["loss"])

        # GPT-2 Medium thresholds (tighter to reduce false positives)
        if pp_medium <= 12:
            score_large = 1.0
        elif pp_medium >= 50:
            score_large = 0.0
        else:
            score_large = 1.0 - ((pp_medium - 12) / 38)

        if pp_distil <= 20:
            score_distil = 1.0
        elif pp_distil >= 70:
            score_distil = 0.0
        else:
            score_distil = 1.0 - ((pp_distil - 20) / 50)

        avg_score = (score_large + score_distil) / 2
        agreement = 1.0 - abs(score_large - score_distil)
        score = avg_score * (0.7 + 0.3 * agreement)
        score = min(max(score, 0.0), 1.0)

        return EngineResult(
            engine_name=self.name,
            score=round(score, 3),
            verdict=score_to_engine_verdict(score),
            details=(
                f"GPT-2 Medium PP: {pp_medium:.1f} (score {score_large:.2f}), "
                f"DistilGPT-2 PP: {pp_distil:.1f} (score {score_distil:.2f}), "
                f"agreement: {agreement:.2f}"
            ),
            description=self.description,
        )
