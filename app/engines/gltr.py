import torch
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


class GLTREngine(BaseEngine):
    @property
    def name(self) -> str:
        return "GLTR"

    @property
    def description(self) -> str:
        return "Token rank distribution — AI text uses disproportionately top-ranked tokens"

    @property
    def code(self) -> str:
        return "GL"

    @property
    def engine_type(self) -> str:
        return "statistical"

    @property
    def url(self) -> str:
        return "https://arxiv.org/abs/1906.04043"

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

        if outputs["logits"] is None or outputs["n_tokens"] < 10:
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details="Text too short for GLTR analysis.",
                description=self.description,
            )

        logits = outputs["logits"]
        input_ids = outputs["input_ids"]
        n_tokens = outputs["n_tokens"]

        pred_logits = logits[0, :-1]
        actual_tokens = input_ids[0, 1:]
        actual_logit_vals = pred_logits.gather(1, actual_tokens.unsqueeze(1))
        ranks = (pred_logits > actual_logit_vals).sum(dim=-1)

        # Use top-1 (argmax) which shows much better AI/human separation
        top1 = (ranks == 0).sum().item()
        top5 = (ranks < 5).sum().item()
        top10 = (ranks < 10).sum().item()
        top100 = (ranks < 100).sum().item()

        pct_top1 = top1 / n_tokens
        pct_top5 = top5 / n_tokens
        pct_top10 = top10 / n_tokens
        pct_top100 = top100 / n_tokens

        # GPT-2 Medium: AI text has ~45-55% top-1 tokens, human ~30-40%
        # Use top-1 as primary signal (better separation than top-10)
        if pct_top1 >= 0.50:
            score = 1.0
        elif pct_top1 <= 0.30:
            score = 0.0
        else:
            score = (pct_top1 - 0.30) / 0.20

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=(
                f"Top-1: {pct_top1:.0%}, Top-5: {pct_top5:.0%}, "
                f"Top-10: {pct_top10:.0%}, Top-100: {pct_top100:.0%} of {n_tokens} tokens"
            ),
            description=self.description,
        )
