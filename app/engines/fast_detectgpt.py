import torch
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


class FastDetectGPTEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Fast-DetectGPT"

    @property
    def description(self) -> str:
        return "Conditional probability curvature — AI tokens sit at peaks of the model's distribution"

    @property
    def code(self) -> str:
        return "FD"

    @property
    def engine_type(self) -> str:
        return "statistical"

    @property
    def url(self) -> str:
        return "https://arxiv.org/abs/2310.05130"

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
                details="Text too short for curvature analysis.",
                description=self.description,
            )

        logits = outputs["logits"]
        input_ids = outputs["input_ids"]
        n_tokens = outputs["n_tokens"]

        pred_logits = logits[0, :-1]
        log_probs = torch.log_softmax(pred_logits, dim=-1)
        probs = torch.softmax(pred_logits, dim=-1)
        actual_tokens = input_ids[0, 1:]

        actual_lp = log_probs.gather(1, actual_tokens.unsqueeze(1)).squeeze()
        expected_lp = (probs * log_probs).sum(dim=-1)
        expected_lp_sq = (probs * log_probs**2).sum(dim=-1)
        variance = (expected_lp_sq - expected_lp**2).clamp(min=1e-10)
        std = torch.sqrt(variance)

        curvature = (actual_lp - expected_lp) / std
        mean_curvature = curvature.mean().item()

        # GPT-2 Medium: AI text curvature ~0.15-0.35, human text ~-0.3 to 0.05
        if mean_curvature >= 0.30:
            score = 1.0
        elif mean_curvature <= 0.0:
            score = 0.0
        else:
            score = mean_curvature / 0.30

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=f"Mean curvature: {mean_curvature:.3f} (higher = more AI-like, n={n_tokens} tokens)",
            description=self.description,
        )
