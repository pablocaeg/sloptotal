import os
import threading
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict
from app.model_pool import ModelPool
from app.autoconfig import get_device

_MODEL_NAME = "ShantanuT01/BERT-tiny-RAID"
_model = None
_tokenizer = None
_lock = threading.Lock()

_pool_size = int(os.getenv("SLOPTOTAL_POOL_BERT_RAID", "1"))
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
    _pool = ModelPool(_load_one_replica, pool_size=_pool_size, name="BERT-RAID")
    _pool.initialize()


def _load_model():
    """Legacy singleton loader — skipped when pooling is active."""
    global _model, _tokenizer
    if _pool_size > 1:
        return None, None
    if _model is None:
        _model, _tokenizer = _load_one_replica()
    return _model, _tokenizer


def _score_chunk(text: str, model, tokenizer) -> float:
    device = next(model.parameters()).device
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.inference_mode():
        logits = model(**inputs).logits
    human_prob = torch.sigmoid(logits[0, 0]).item()
    return 1.0 - human_prob


def _score_batch(texts: list[str], model, tokenizer) -> list[float]:
    """Batch inference — single forward pass for N texts."""
    device = next(model.parameters()).device
    inputs = tokenizer(
        texts, return_tensors="pt", truncation=True, max_length=512, padding=True
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.inference_mode():
        logits = model(**inputs).logits
    human_probs = torch.sigmoid(logits[:, 0])
    return [(1.0 - p.item()) for p in human_probs]


def _run_inference(text: str, model, tokenizer) -> float:
    """Run chunked inference on text, return AI probability score."""
    tokens = tokenizer.encode(text, add_special_tokens=False)

    if len(tokens) <= 510:
        return _score_chunk(text, model, tokenizer)

    stride = 256
    window = 510
    chunk_scores = []
    for start in range(0, len(tokens), stride):
        chunk_ids = tokens[start : start + window]
        if len(chunk_ids) < 20:
            break
        chunk_text = tokenizer.decode(chunk_ids, skip_special_tokens=True)
        chunk_scores.append(_score_chunk(chunk_text, model, tokenizer))
    return sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0


class ClassifierBERTRaidEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "BERT-tiny RAID"

    @property
    def description(self) -> str:
        return "BERT-tiny (4.4M params) trained on RAID dataset — ultra-fast inference"

    @property
    def code(self) -> str:
        return "BT"

    @property
    def url(self) -> str:
        return "https://huggingface.co/ShantanuT01/BERT-tiny-RAID"

    def analyze_batch(self, texts: list[str]) -> list[float]:
        """Batch score multiple short texts. Returns raw AI probability scores."""
        if _pool is not None:
            with _pool.acquire() as (model, tokenizer):
                return _score_batch(texts, model, tokenizer)
        else:
            model, tokenizer = _load_model()
            with _lock:
                return _score_batch(texts, model, tokenizer)

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
            details=f"AI probability: {score:.1%} (BERT-tiny, RAID dataset)",
            description=self.description,
        )
