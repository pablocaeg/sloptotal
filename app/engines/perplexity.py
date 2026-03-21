import math
import threading
import torch
from transformers import GPT2LMHeadModel, GPT2TokenizerFast
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict
from app.config import GPT2_MODEL

_model = None
_tokenizer = None
_lock = threading.Lock()


def _load_model():
    global _model, _tokenizer
    if _model is None:
        _tokenizer = GPT2TokenizerFast.from_pretrained(GPT2_MODEL)
        _model = GPT2LMHeadModel.from_pretrained(GPT2_MODEL)
        _model.eval()
    return _model, _tokenizer


class PerplexityEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Perplexity"

    @property
    def description(self) -> str:
        return "GPT-2 perplexity scoring — low perplexity suggests AI-generated text"

    @property
    def code(self) -> str:
        return "PP"

    @property
    def engine_type(self) -> str:
        return "statistical"

    @property
    def url(self) -> str:
        return "https://huggingface.co/openai-community/gpt2-medium"

    def analyze(self, text: str) -> EngineResult:
        try:
            _load_model()
            from app.engines.gpt2_cache import get_gpt2_outputs

            outputs = get_gpt2_outputs(text)
        except Exception as e:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details=f"Model loading failed: {e}",
                description=self.description,
            )

        if outputs["loss"] is None:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Text too short for perplexity analysis.",
                description=self.description,
            )

        perplexity = math.exp(outputs["loss"])

        # GPT-2 Medium: AI text ~8-20 PP, well-written human ~25-50, casual human 50+
        if perplexity <= 12:
            score = 1.0
        elif perplexity >= 50:
            score = 0.0
        else:
            score = 1.0 - ((perplexity - 12) / 38)

        return EngineResult(
            engine_name=self.name,
            score=round(score, 3),
            verdict=score_to_engine_verdict(score),
            details=f"Perplexity: {perplexity:.1f} (lower = more likely AI-generated)",
            description=self.description,
        )
