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

        # Calibrated on 108 RAID samples (72 AI, 36 human), 2026-07-25:
        #
        #              p10     median    p90
        #   AI        0.853    0.986    1.130
        #   human     0.857    0.908    0.983
        #
        # Two separate faults were corrected here:
        #
        # 1. Direction. This engine's premise -- "AI text has unnaturally
        #    uniform per-token surprisal", so a LOW CV means AI -- does not hold
        #    for GPT-2 Medium on this corpus. AI text measured a *higher*
        #    surprisal CV than human text, and the old ramp scored downwards.
        # 2. Range. The old band (0.55-0.85) sat entirely below both observed
        #    distributions, so nearly every real input clamped to 0.0 and the
        #    engine emitted a near-constant score regardless of provenance.
        #
        # Together those gave AUC 0.432 -- marginally worse than a coin flip.
        # Separation is genuinely modest (the distributions overlap heavily),
        # which is why this engine keeps only a small ensemble weight.
        CV_LOW, CV_HIGH = 0.87, 1.13
        cv_score = min(max((cv - CV_LOW) / (CV_HIGH - CV_LOW), 0.0), 1.0)

        # Skew is retained as a weak secondary term, but it did not separate the
        # classes on its own in the same measurement, so it can no longer drive
        # the score to 1.0 by itself.
        abs_skew = abs(skew_s)
        if abs_skew <= 0.3:
            skew_score = 0.5
        elif abs_skew >= 1.5:
            skew_score = 0.0
        else:
            skew_score = 0.5 - ((abs_skew - 0.3) / 1.2) * 0.5

        score = cv_score * 0.85 + skew_score * 0.15

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
