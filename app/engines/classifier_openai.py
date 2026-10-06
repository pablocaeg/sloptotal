import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from app.engines.base import BaseEngine, FairLock, score_in_windows
from app.schemas import EngineResult, score_to_engine_verdict
from app.model_pool import LOAD_LOCK as _load_lock

_MODEL_NAME = "roberta-base-openai-detector"
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
                model.eval()
                # Publish the model last: readers test it, so the tokenizer must
                # already be set and the model already in eval mode when they see it.
                _model = model
    return _model, _tokenizer


def _score_chunk(text: str, model, tokenizer) -> float:
    """Score a single chunk and return AI probability."""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0]
    # Label mapping: 0 = Real, 1 = Fake (AI-generated)
    id2label = model.config.id2label
    fake_idx = None
    for idx, label in id2label.items():
        if "fake" in str(label).lower():
            fake_idx = int(idx)
            break
    if fake_idx is None:
        fake_idx = 1
    return probs[fake_idx].item()


class ClassifierOpenAIEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "OpenAI Detector"

    @property
    def description(self) -> str:
        return "RoBERTa fine-tuned by OpenAI to detect GPT-generated text"

    @property
    def code(self) -> str:
        return "OA"

    @property
    def engine_type(self) -> str:
        return "classifier"

    @property
    def url(self) -> str:
        return "https://huggingface.co/roberta-base-openai-detector"

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
            text, tokenizer, lambda chunk: _score_chunk(chunk, model, tokenizer), _lock
        )

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=f"AI probability: {score:.1%} (RoBERTa OpenAI detector)",
            description=self.description,
        )
