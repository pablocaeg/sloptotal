import os
import threading
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict
from app.model_pool import ModelPool
from app.autoconfig import get_device

_MODEL_NAME = "fakespot-ai/roberta-base-ai-text-detection-v1"
_model = None
_tokenizer = None
_lock = threading.Lock()

_pool_size = int(os.getenv("SLOPTOTAL_POOL_FAKESPOT", "1"))
_pool: ModelPool | None = None


def _load_one_replica():
    """Create a fresh, independent (model, tokenizer) pair."""
    device = get_device()
    t = AutoTokenizer.from_pretrained(_MODEL_NAME)
    m = AutoModelForSequenceClassification.from_pretrained(_MODEL_NAME)
    m.eval().to(device)
    return m, t


def _init_pool():
    """Called by preloader to eagerly load replicas."""
    global _pool
    if _pool_size <= 1:
        _load_model()
        return
    _pool = ModelPool(_load_one_replica, pool_size=_pool_size, name="Fakespot")
    _pool.initialize()


def _load_model():
    """Legacy singleton loader — skipped when pooling is active."""
    global _model, _tokenizer
    if _pool_size > 1:
        return None, None
    if _model is None:
        _model, _tokenizer = _load_one_replica()
    return _model, _tokenizer


def _get_ai_index(model) -> int:
    """Find the label index corresponding to AI-generated text."""
    id2label = getattr(model.config, "id2label", {})
    for idx, label in id2label.items():
        label_lower = str(label).lower()
        if any(kw in label_lower for kw in ("ai", "fake", "generated", "machine")):
            return int(idx)
    return 1


def _score_chunk(text: str, model, tokenizer, ai_idx: int) -> float:
    device = next(model.parameters()).device
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.inference_mode():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0]
    return probs[ai_idx].item()


def _score_batch(texts: list[str], model, tokenizer, ai_idx: int) -> list[float]:
    """Batch inference — single forward pass for N texts."""
    device = next(model.parameters()).device
    inputs = tokenizer(
        texts, return_tensors="pt", truncation=True, max_length=512, padding=True
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.inference_mode():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)
    return [probs[i][ai_idx].item() for i in range(len(texts))]


def _run_inference(text: str, model, tokenizer) -> float:
    """Run chunked inference on text, return AI probability score."""
    ai_idx = _get_ai_index(model)
    tokens = tokenizer.encode(text, add_special_tokens=False)

    if len(tokens) <= 510:
        return _score_chunk(text, model, tokenizer, ai_idx)

    stride = 256
    window = 510
    chunk_scores = []
    for start in range(0, len(tokens), stride):
        chunk_ids = tokens[start : start + window]
        if len(chunk_ids) < 20:
            break
        chunk_text = tokenizer.decode(chunk_ids, skip_special_tokens=True)
        chunk_scores.append(_score_chunk(chunk_text, model, tokenizer, ai_idx))
    return sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0


class ClassifierFakespotEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Fakespot"

    @property
    def description(self) -> str:
        return "RoBERTa-base AI text detector from the APOLLO system"

    @property
    def code(self) -> str:
        return "FS"

    @property
    def url(self) -> str:
        return "https://huggingface.co/fakespot-ai/roberta-base-ai-text-detection-v1"

    def analyze_batch(self, texts: list[str]) -> list[float]:
        """Batch score multiple short texts. Returns raw AI probability scores."""
        if _pool is not None:
            with _pool.acquire() as (model, tokenizer):
                ai_idx = _get_ai_index(model)
                return _score_batch(texts, model, tokenizer, ai_idx)
        else:
            model, tokenizer = _load_model()
            with _lock:
                ai_idx = _get_ai_index(model)
                return _score_batch(texts, model, tokenizer, ai_idx)

    def analyze(self, text: str) -> EngineResult:
        try:
            if _pool is not None:
                with _pool.acquire() as (model, tokenizer):
                    score = _run_inference(text, model, tokenizer)
            else:
                model, tokenizer = _load_model()
                with _lock:
                    score = _run_inference(text, model, tokenizer)
        except Exception as e:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details=f"Model loading failed: {e}",
                description=self.description,
            )

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=f"AI probability: {score:.1%} (Fakespot APOLLO RoBERTa)",
            description=self.description,
        )
