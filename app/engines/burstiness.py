import math
import re
import statistics
import torch
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


class BurstinessEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Burstiness"

    @property
    def description(self) -> str:
        return "Measures per-sentence perplexity variance — flat rhythm suggests AI"

    @property
    def code(self) -> str:
        return "BU"

    @property
    def engine_type(self) -> str:
        return "linguistic"

    def analyze(self, text: str) -> EngineResult:
        try:
            from app.engines.gpt2_cache import get_gpt2_outputs

            outputs = get_gpt2_outputs(text)
        except Exception as e:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details=f"Model failed: {e}",
                description=self.description,
            )

        if outputs["logits"] is None or outputs["n_tokens"] < 20:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Text too short for burstiness analysis.",
                description=self.description,
            )

        # Split text into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if len(s.strip().split()) >= 5]

        if len(sentences) < 5:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Not enough sentences for burstiness analysis.",
                description=self.description,
            )

        # Compute per-token cross-entropy from cached forward pass
        logits = outputs["logits"]
        input_ids = outputs["input_ids"]

        log_probs = torch.log_softmax(logits[0, :-1], dim=-1)
        actual_tokens = input_ids[0, 1:]
        token_losses = -log_probs.gather(1, actual_tokens.unsqueeze(1)).squeeze()

        # Map sentence boundaries to token positions using the tokenizer
        from app.engines.perplexity import _load_model

        _, tokenizer = _load_model()

        # Tokenize each sentence to find its length in tokens
        sentence_pps = []
        token_offset = 0
        full_token_count = token_losses.size(0)

        for sent in sentences:
            sent_tokens = tokenizer.encode(sent, add_special_tokens=False)
            sent_len = len(sent_tokens)

            if token_offset + sent_len > full_token_count:
                sent_len = full_token_count - token_offset

            if sent_len >= 4:
                sent_losses = token_losses[token_offset : token_offset + sent_len]
                mean_loss = sent_losses.mean().item()
                sentence_pps.append(math.exp(mean_loss))

            token_offset += sent_len
            if token_offset >= full_token_count:
                break

        if len(sentence_pps) < 4:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Could not compute enough sentence perplexities.",
                description=self.description,
            )

        mean_pp = statistics.mean(sentence_pps)
        stdev_pp = statistics.stdev(sentence_pps)
        cv = stdev_pp / mean_pp if mean_pp > 0 else 0

        # Low CV = uniform/flat = AI-like
        # Human CV typically 0.5-1.5+, AI CV typically 0.1-0.4
        if cv <= 0.15:
            score = 1.0
        elif cv >= 0.8:
            score = 0.0
        else:
            score = 1.0 - ((cv - 0.15) / 0.65)

        details = (
            f"Sentence perplexity CV: {cv:.3f} "
            f"(mean={mean_pp:.1f}, stdev={stdev_pp:.1f}, n={len(sentence_pps)} sentences). "
            f"{'Flat rhythm — AI-like' if score > 0.5 else 'Natural variation — human-like'}"
        )

        return EngineResult(
            engine_name=self.name,
            score=round(score, 3),
            verdict=score_to_engine_verdict(score),
            details=details,
            description=self.description,
        )
