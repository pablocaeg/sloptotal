import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.autoconfig import get_device
from app.engines.base import (
    LARGE_MODEL_MAX_WINDOWS,
    BaseEngine,
    FairLock,
    score_in_windows,
)
from app.model_pool import LOAD_LOCK as _load_lock
from app.schemas import EngineResult, score_to_engine_verdict

_MODEL_NAME = "hyunseoki/ReMoDetect-deberta"
_model = None
_tokenizer = None
_lock = FairLock()


def _load_model():
    global _model, _tokenizer
    if _model is None:
        with _load_lock:
            if _model is None:
                _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
                model = AutoModelForSequenceClassification.from_pretrained(_MODEL_NAME)
                model.eval().to(get_device())
                # Publish the model last: readers test it, so the tokenizer must
                # already be set and the model already in eval mode when they see it.
                _model = model
    return _model, _tokenizer


def _score_chunk(text: str, model, tokenizer) -> float:
    device = next(model.parameters()).device
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits

    # ReMoDetect is a single-output regression model (num_labels=1)
    # Higher reward score → more likely RLHF-aligned AI text
    if logits.shape[-1] == 1:
        return torch.sigmoid(logits[0, 0]).item()
    else:
        probs = torch.softmax(logits, dim=-1)[0]
        return probs[-1].item()


class ClassifierReMoDetectEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "ReMoDetect"

    @property
    def description(self) -> str:
        return "Reward-model detector targeting RLHF-aligned LLMs (GPT-4, Claude, Llama-chat)"

    @property
    def code(self) -> str:
        return "RM"

    @property
    def url(self) -> str:
        return "https://huggingface.co/hyunseoki/ReMoDetect-deberta"

    def analyze(self, text: str) -> EngineResult:
        try:
            model, tokenizer = _load_model()
        except Exception as e:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details=f"Model loading failed: {e}",
                description=self.description,
            )

        score = score_in_windows(
            text,
            tokenizer,
            lambda chunk: _score_chunk(chunk, model, tokenizer),
            _lock,
            stride=510,
            max_windows=LARGE_MODEL_MAX_WINDOWS,
        )

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=f"AI probability: {score:.1%} (RLHF reward-model detector)",
            description=self.description,
        )
