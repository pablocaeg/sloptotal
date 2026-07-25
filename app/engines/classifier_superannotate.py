import threading
import torch
import torch.nn as nn
from transformers import (
    AutoTokenizer,
    AutoConfig,
    AutoModel,
    PreTrainedModel,
)
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

_MODEL_NAME = "SuperAnnotate/ai-detector-low-fpr"
_BASE_NAME = "FacebookAI/roberta-large"
_model = None
_tokenizer = None
_lock = threading.Lock()


class _SuperAnnotateDetector(PreTrainedModel):
    """Matches the checkpoint's real layout: RoBERTa-large + a `dense` head.

    The 391 tensors are `roberta.*` (389) plus `dense.weight` (1, 1024) and
    `dense.bias` — a single-logit classifier over the <s> token, named `dense`
    at the top level.

    This must NOT be loaded with RobertaForSequenceClassification, which is what
    this engine did. That class looks for `classifier.dense.*` and
    `classifier.out_proj.*`, so the checkpoint's trained head was silently
    discarded as UNEXPECTED and a fresh head randomly initialised in its place.

    The consequence was worse than noise. Measured on 110 RAID samples across
    news/books/poetry/abstracts, the engine scored AUC 0.037 -- almost perfectly
    *inverted*, rating human text above AI -- while holding 6% of the ensemble
    weight and being described as "optimized for low false-positive rate".

    An abstracts-only corpus had shown AUC 1.000 for this engine, which is how
    the fault stayed hidden; a random projection can rank one narrow domain well
    by luck. Always evaluate across domains.

    Loaded correctly it is one of the strongest engines, and it carries no bias
    against archaic prose: AI slop 0.9995, Austen (1813) 0.0009,
    Melville (1851) 0.0029.
    """

    config_class = AutoConfig

    def __init__(self, config):
        super().__init__(config)
        # No pooler: the head reads the <s> hidden state directly.
        self.roberta = AutoModel.from_config(config, add_pooling_layer=False)
        self.dense = nn.Linear(config.hidden_size, 1)
        self.post_init()

    def forward(self, input_ids, attention_mask=None, **kwargs):
        outputs = self.roberta(input_ids=input_ids, attention_mask=attention_mask)
        cls = outputs.last_hidden_state[:, 0]  # <s>, RoBERTa's sequence summary
        return self.dense(cls)


def _load_model():
    global _model, _tokenizer
    if _model is None:
        # The repo's config.json has no model_type, so the architecture cannot be
        # inferred from it; take the base config and load the weights over it.
        config = AutoConfig.from_pretrained(_BASE_NAME)
        _tokenizer = AutoTokenizer.from_pretrained(_BASE_NAME)
        _model = _SuperAnnotateDetector.from_pretrained(_MODEL_NAME, config=config)
        _model.eval()
    return _model, _tokenizer


def _score_chunk(text: str, model, tokenizer) -> float:
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
        )
    # Single logit; config id2label is {0: "GENERATED"}, so sigmoid is P(AI).
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
