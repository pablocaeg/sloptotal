"""BurstinessEngine's early returns, with GPT-2 stubbed out.

The engine needs GPT-2 outputs for its real scoring, so those paths are measured
in tests/eval/. The three early returns that give a score of 0 happen before any
model output is used, so they can be pinned down here without downloading a model.
"""

import pytest

from app.engines.burstiness import BurstinessEngine
from app.schemas import Verdict

# Five words per sentence, so each counts towards the five-sentence minimum.
FIVE_SENTENCES = " ".join(["The quick brown fox jumps."] * 5)
THREE_SENTENCES = " ".join(["The quick brown fox jumps."] * 3)


def stub_gpt2(monkeypatch, outputs=None, error=None):
    """Replace the cached GPT-2 forward pass the engine imports inside analyze()."""

    def fake_get_gpt2_outputs(text):
        if error is not None:
            raise error
        return outputs

    monkeypatch.setattr(
        "app.engines.gpt2_cache.get_gpt2_outputs", fake_get_gpt2_outputs
    )


def assert_zero_score(result, details):
    assert result.engine_name == "Burstiness"
    assert result.score == 0.0
    assert result.verdict == Verdict.CLEAN
    assert result.details == details


def test_model_failure_gives_zero_score(monkeypatch):
    stub_gpt2(monkeypatch, error=RuntimeError("weights missing"))

    result = BurstinessEngine().analyze(FIVE_SENTENCES)

    assert_zero_score(result, "Model failed: weights missing")


def test_missing_logits_is_too_short(monkeypatch):
    stub_gpt2(monkeypatch, outputs={"logits": None, "n_tokens": 0})

    result = BurstinessEngine().analyze(FIVE_SENTENCES)

    assert_zero_score(result, "Text too short for burstiness analysis.")


@pytest.mark.parametrize("n_tokens", [0, 19])
def test_fewer_than_twenty_tokens_is_too_short(monkeypatch, n_tokens):
    stub_gpt2(monkeypatch, outputs={"logits": object(), "n_tokens": n_tokens})

    result = BurstinessEngine().analyze(FIVE_SENTENCES)

    assert_zero_score(result, "Text too short for burstiness analysis.")


def test_fewer_than_five_sentences_is_not_enough(monkeypatch):
    stub_gpt2(monkeypatch, outputs={"logits": object(), "n_tokens": 20})

    result = BurstinessEngine().analyze(THREE_SENTENCES)

    assert_zero_score(result, "Not enough sentences for burstiness analysis.")


def test_sentences_under_five_words_do_not_count(monkeypatch):
    stub_gpt2(monkeypatch, outputs={"logits": object(), "n_tokens": 20})
    text = " ".join(["Too short here."] * 8) + " " + THREE_SENTENCES

    result = BurstinessEngine().analyze(text)

    assert_zero_score(result, "Not enough sentences for burstiness analysis.")
