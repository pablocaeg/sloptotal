"""Diagnose actual values from broken engines to find correct thresholds."""
import sys
sys.path.insert(0, "/root/sloptotal")

AI_TEXT = (
    "Artificial intelligence has transformed numerous industries in recent years, "
    "fundamentally reshaping the way we approach complex problems. From healthcare to finance, "
    "the applications of machine learning and deep learning have proven to be remarkably versatile. "
    "One of the most significant developments in this field has been the emergence of large language "
    "models, which have demonstrated an unprecedented ability to generate human-like text."
)

HUMAN_TEXT = (
    "ok so basically I've been trying to fix this stupid bug for like 3 hours and I finally "
    "figured out what was wrong. turns out I had a typo in my env variable name... POSTGRES_HOST "
    "vs POSTGRESS_HOST (two s's lmao). The error message was completely unhelpful btw, it just "
    "said 'connection refused' which made me think it was a firewall issue so I spent forever "
    "checking iptables and docker networking stuff."
)

HUMAN_TEXT2 = (
    "Look, I know everyone's excited about microservices but can we talk about when they're "
    "actually a terrible idea? I've seen three startups this year blow months of engineering "
    "time decomposing a monolith that was working fine. The thing is, microservices solve "
    "organizational problems, not technical ones."
)

import torch
from app.engines.gpt2_cache import get_gpt2_outputs

for label, text in [("AI", AI_TEXT), ("HUMAN", HUMAN_TEXT), ("HUMAN2", HUMAN_TEXT2)]:
    outputs = get_gpt2_outputs(text)
    logits = outputs["logits"]
    input_ids = outputs["input_ids"]
    n_tokens = outputs["n_tokens"]

    pred_logits = logits[0, :-1]
    actual_tokens = input_ids[0, 1:]
    actual_logit_vals = pred_logits.gather(1, actual_tokens.unsqueeze(1))
    ranks = (pred_logits > actual_logit_vals).sum(dim=-1)

    # GLTR
    top10 = (ranks < 10).sum().item()
    pct_top10 = top10 / n_tokens
    print(f"\n=== {label} (n={n_tokens}) ===")
    print(f"GLTR top-10%: {pct_top10:.3f}")

    # Log-Rank
    log_ranks = torch.log(ranks.float() + 1)
    mean_log_rank = log_ranks.mean().item()
    print(f"Log-Rank mean: {mean_log_rank:.3f}")

    # Fast-DetectGPT curvature
    log_probs = torch.log_softmax(pred_logits, dim=-1)
    probs = torch.softmax(pred_logits, dim=-1)
    actual_lp = log_probs.gather(1, actual_tokens.unsqueeze(1)).squeeze()
    expected_lp = (probs * log_probs).sum(dim=-1)
    expected_lp_sq = (probs * log_probs ** 2).sum(dim=-1)
    variance = (expected_lp_sq - expected_lp ** 2).clamp(min=1e-10)
    std = torch.sqrt(variance)
    curvature = (actual_lp - expected_lp) / std
    mean_curvature = curvature.mean().item()
    print(f"Fast-DetectGPT curvature: {mean_curvature:.4f}")

    # Binoculars
    from app.engines.gpt2_cache import get_distil_outputs
    import math
    gpt2 = outputs
    distil = get_distil_outputs(text)
    ce_perf = gpt2["loss"]
    ce_obs = distil["loss"]
    ratio = ce_obs / max(ce_perf, 1e-6)
    print(f"Binoculars CE ratio: {ratio:.4f} (performer={ce_perf:.3f}, observer={ce_obs:.3f})")

    # DivEye
    surprisals = (-log_probs.gather(1, actual_tokens.unsqueeze(1)).squeeze()).tolist()
    if isinstance(surprisals, float):
        surprisals = [surprisals]
    mean_s = sum(surprisals) / len(surprisals)
    diffs = [x - mean_s for x in surprisals]
    var_s = sum(d**2 for d in diffs) / len(diffs)
    std_s = var_s ** 0.5 if var_s > 0 else 1e-10
    cv = std_s / mean_s if mean_s > 0 else 0
    skew = (sum(d**3 for d in diffs) / len(diffs)) / (std_s**3) if std_s > 1e-10 else 0
    print(f"DivEye CV: {cv:.4f}, skew: {skew:.4f}")

    # Desklib
    from app.engines.classifier_desklib import _load_model, _score_chunk, _lock
    model, tokenizer = _load_model()
    with _lock:
        dscore = _score_chunk(text, model, tokenizer)
    print(f"Desklib raw score: {dscore:.4f}")

from app.engines.gpt2_cache import clear_caches
clear_caches()
