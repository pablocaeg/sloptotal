import threading
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

_MODEL_NAME = "Hello-SimpleAI/chatgpt-detector-roberta"
_model = None
_tokenizer = None
_lock = threading.Lock()


def _load_model():
    global _model, _tokenizer
    if _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(_MODEL_NAME)
        _model.eval()
    return _model, _tokenizer


def _get_ai_label_index(model) -> int:
    """Auto-detect which label index corresponds to AI/ChatGPT text."""
    id2label = model.config.id2label
    for idx, label in id2label.items():
        label_lower = str(label).lower()
        if "chatgpt" in label_lower or "ai" in label_lower or "fake" in label_lower:
            return int(idx)
    # Fallback: assume last label is the AI class
    return max(int(k) for k in id2label.keys())


def _score_chunk(text: str, model, tokenizer, ai_idx: int) -> float:
    """Score a single chunk and return AI probability."""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0]
    return probs[ai_idx].item()


class ClassifierChatGPTEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "ChatGPT Detector"

    @property
    def description(self) -> str:
        return "RoBERTa trained specifically on ChatGPT-generated text"

    @property
    def code(self) -> str:
        return "CG"

    @property
    def engine_type(self) -> str:
        return "classifier"

    @property
    def url(self) -> str:
        return "https://huggingface.co/Hello-SimpleAI/chatgpt-detector-roberta"

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

        ai_idx = _get_ai_label_index(model)

        with _lock:
            tokens = tokenizer.encode(text, add_special_tokens=False)

            if len(tokens) <= 510:
                score = _score_chunk(text, model, tokenizer, ai_idx)
            else:
                stride = 256
                window = 510
                chunk_scores = []
                for start in range(0, len(tokens), stride):
                    chunk_ids = tokens[start : start + window]
                    if len(chunk_ids) < 20:
                        break
                    chunk_text = tokenizer.decode(chunk_ids, skip_special_tokens=True)
                    chunk_scores.append(
                        _score_chunk(chunk_text, model, tokenizer, ai_idx)
                    )
                score = sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0

        label_name = model.config.id2label.get(ai_idx, "AI")

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=f"AI probability: {score:.1%} (ChatGPT detector, label='{label_name}')",
            description=self.description,
        )
