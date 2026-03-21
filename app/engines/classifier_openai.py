import threading
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

_MODEL_NAME = "roberta-base-openai-detector"
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

        with _lock:
            # Tokenize full text to determine if chunking is needed
            tokens = tokenizer.encode(text, add_special_tokens=False)

            if len(tokens) <= 510:
                score = _score_chunk(text, model, tokenizer)
            else:
                # Chunked scoring with stride for long texts
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
            details=f"AI probability: {score:.1%} (RoBERTa OpenAI detector)",
            description=self.description,
        )
