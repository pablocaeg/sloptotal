import threading
import torch
from transformers import (
    RobertaTokenizer,
    RobertaForSequenceClassification,
    RobertaConfig,
)
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

_MODEL_NAME = "SuperAnnotate/ai-detector-low-fpr"
_model = None
_tokenizer = None
_lock = threading.Lock()


def _load_model():
    global _model, _tokenizer
    if _model is None:
        # Model config is missing model_type — use roberta-large config with num_labels=1
        config = RobertaConfig.from_pretrained("FacebookAI/roberta-large", num_labels=1)
        _tokenizer = RobertaTokenizer.from_pretrained("FacebookAI/roberta-large")
        _model = RobertaForSequenceClassification.from_pretrained(
            _MODEL_NAME,
            config=config,
        )
        _model.eval()
    return _model, _tokenizer


def _score_chunk(text: str, model, tokenizer) -> float:
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    # num_labels=1, label 0="GENERATED" — sigmoid = probability of AI-generated
    return torch.sigmoid(logits[0, 0]).item()


class ClassifierSuperAnnotateEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "SuperAnnotate"

    @property
    def description(self) -> str:
        return "RoBERTa-large optimized for low false-positive rate — RAID benchmark"

    @property
    def code(self) -> str:
        return "SN"

    @property
    def url(self) -> str:
        return "https://huggingface.co/SuperAnnotate/ai-detector"

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

        with _lock:
            tokens = tokenizer.encode(text, add_special_tokens=False)

            if len(tokens) <= 510:
                score = _score_chunk(text, model, tokenizer)
            else:
                stride = 256
                window = 510
                chunk_scores = []
                for start in range(0, len(tokens), stride):
                    chunk_ids = tokens[start : start + window]
                    if len(chunk_ids) < 20:
                        break
                    chunk_text = tokenizer.decode(chunk_ids, skip_special_tokens=True)
                    chunk_scores.append(_score_chunk(chunk_text, model, tokenizer))
                score = sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=f"AI probability: {score:.1%} (SuperAnnotate RoBERTa-large, low FPR)",
            description=self.description,
        )
