import torch
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


class LogRankEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Log-Rank"

    @property
    def description(self) -> str:
        return "Average log-rank of tokens under GPT-2 — lower rank means more predictable (AI-like)"

    @property
    def code(self) -> str:
        return "LR"

    @property
    def engine_type(self) -> str:
        return "statistical"

    @property
    def url(self) -> str:
        return "https://huggingface.co/openai-community/gpt2-medium"

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
                details="Text too short for log-rank analysis.",
                description=self.description,
            )

        logits = outputs["logits"]
        input_ids = outputs["input_ids"]
        n_tokens = outputs["n_tokens"]

        pred_logits = logits[0, :-1]
        actual_tokens = input_ids[0, 1:]
        actual_logit_vals = pred_logits.gather(1, actual_tokens.unsqueeze(1))
        ranks = (pred_logits > actual_logit_vals).sum(dim=-1).float()

        log_ranks = torch.log(ranks + 1)
        mean_log_rank = log_ranks.mean().item()

        # GPT-2 Medium: AI text ~1.0-1.4, human text ~1.6-2.5+
        if mean_log_rank <= 1.2:
            score = 1.0
        elif mean_log_rank >= 2.2:
            score = 0.0
        else:
            score = 1.0 - ((mean_log_rank - 1.2) / 1.0)

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=f"Mean log-rank: {mean_log_rank:.2f} (lower = more AI-like, n={n_tokens} tokens)",
            description=self.description,
        )
