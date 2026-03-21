import threading
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

_MODEL_NAME = "desklib/ai-text-detector-v1.01"
_model = None
_tokenizer = None
_lock = threading.Lock()


_num_labels = None


def _load_model():
    global _model, _tokenizer, _num_labels
    if _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
        # Checkpoint has a 1-output classifier head — load with num_labels=1
        _model = AutoModelForSequenceClassification.from_pretrained(
            _MODEL_NAME,
            num_labels=1,
        )
        _model.eval()
        _num_labels = 1
    return _model, _tokenizer


def _score_chunk(text: str, model, tokenizer) -> float:
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits

    if _num_labels == 1 or logits.shape[-1] == 1:
        return torch.sigmoid(logits[0, 0]).item()
    else:
        probs = torch.softmax(logits, dim=-1)[0]
        id2label = getattr(model.config, "id2label", {})
        ai_idx = 1
        for idx, label in id2label.items():
            if any(
                kw in str(label).lower()
                for kw in ("ai", "fake", "generated", "machine")
            ):
                ai_idx = int(idx)
                break
        return probs[ai_idx].item()


class ClassifierDesklibEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Desklib DeBERTa"

    @property
    def description(self) -> str:
        return "DeBERTa-v3-large fine-tuned on GPT-4, Claude, Llama — RAID benchmark leader"

    @property
    def code(self) -> str:
        return "DL"

    @property
    def url(self) -> str:
        return "https://huggingface.co/desklib/ai-text-detector-v1.01"

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
            details=f"AI probability: {score:.1%} (DeBERTa-v3-large, RAID benchmark leader)",
            description=self.description,
        )
