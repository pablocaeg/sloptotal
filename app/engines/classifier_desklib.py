import threading
import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoConfig, AutoModel, PreTrainedModel
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

_MODEL_NAME = "desklib/ai-text-detector-v1.01"
_model = None
_tokenizer = None
_lock = threading.Lock()


class _DesklibAIDetectionModel(PreTrainedModel):
    """Reimplementation of the checkpoint's own `DesklibAIDetectionModel`.

    The published weights are a DeBERTa-v3-large backbone stored under `model.*`
    plus a single-logit `classifier` of shape (1, 1024) applied to the
    mean-pooled last hidden state.

    This must NOT be loaded with AutoModelForSequenceClassification, which is
    what this engine did before. That class expects the backbone under
    `deberta.*` and a 2-way head, so all 392 tensors mismatch: transformers
    reports every one MISSING and randomly initialises the whole network. The
    engine then returned sigmoid(~0) -- roughly 0.5 for any input, AI or human
    -- while carrying 8% of the ensemble weight as a "Tier A" engine.
    """

    config_class = AutoConfig

    def __init__(self, config):
        super().__init__(config)
        self.model = AutoModel.from_config(config)
        self.classifier = nn.Linear(config.hidden_size, 1)
        self.post_init()

    def forward(self, input_ids, attention_mask=None, **kwargs):
        outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
        last_hidden = outputs.last_hidden_state
        # Mean-pool over real tokens only; padding must not drag the mean down.
        mask = attention_mask.unsqueeze(-1).to(last_hidden.dtype)
        pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return self.classifier(pooled)


def _load_model():
    global _model, _tokenizer
    if _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
        config = AutoConfig.from_pretrained(_MODEL_NAME)
        _model = _DesklibAIDetectionModel.from_pretrained(_MODEL_NAME, config=config)
        _model.eval()
    return _model, _tokenizer


def _score_chunk(text: str, model, tokenizer) -> float:
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
        )
    return torch.sigmoid(logits[0, 0]).item()


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
