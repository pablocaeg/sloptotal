import math
import torch
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


def _compute_stats(values: list[float]) -> tuple[float, float, float, float]:
    """Compute mean, std, skewness, kurtosis from a list of values."""
    n = len(values)
    if n < 4:
        return 0.0, 0.0, 0.0, 0.0
    mean = sum(values) / n
    diffs = [x - mean for x in values]
    var = sum(d**2 for d in diffs) / n
    std = math.sqrt(var) if var > 0 else 1e-10
    skew = (sum(d**3 for d in diffs) / n) / (std**3) if std > 1e-10 else 0.0
    kurt = (sum(d**4 for d in diffs) / n) / (std**4) - 3.0 if std > 1e-10 else 0.0
    return mean, std, skew, kurt


class DivEyeEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "DivEye"

    @property
    def description(self) -> str:
        return (
            "Surprisal diversity — AI text has unnaturally uniform per-token surprisal"
        )

    @property
    def code(self) -> str:
        return "DE"

    @property
    def engine_type(self) -> str:
        return "statistical"

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
                details="Text too short for surprisal analysis.",
                description=self.description,
            )

        logits = outputs["logits"]
        input_ids = outputs["input_ids"]
        n_tokens = outputs["n_tokens"]

        log_probs = torch.log_softmax(logits[0, :-1], dim=-1)
        actual_tokens = input_ids[0, 1:]
        surprisals = (
            -log_probs.gather(1, actual_tokens.unsqueeze(1)).squeeze()
        ).tolist()

        if isinstance(surprisals, float):
            surprisals = [surprisals]

        mean_s, std_s, skew_s, kurt_s = _compute_stats(surprisals)

        cv = std_s / mean_s if mean_s > 0 else 0.0

        # GPT-2 Medium: AI CV ~0.50-0.70, human CV ~0.80-1.0+
        if cv <= 0.55:
            cv_score = 1.0
        elif cv >= 0.85:
            cv_score = 0.0
        else:
            cv_score = 1.0 - ((cv - 0.55) / 0.30)

        abs_skew = abs(skew_s)
        if abs_skew <= 0.3:
            skew_score = 1.0
        elif abs_skew >= 1.5:
            skew_score = 0.0
        else:
            skew_score = 1.0 - ((abs_skew - 0.3) / 1.2)

        score = cv_score * 0.7 + skew_score * 0.3

        return EngineResult(
            engine_name=self.name,
            score=round(min(max(score, 0.0), 1.0), 3),
            verdict=score_to_engine_verdict(score),
            details=(
                f"Surprisal CV: {cv:.3f}, skew: {skew_s:.2f}, kurtosis: {kurt_s:.2f} "
                f"(mean={mean_s:.1f}, std={std_s:.1f}, n={n_tokens})"
            ),
            description=self.description,
        )
