"""The order engines are queued in, and when the overall score is final.

The executors are FIFO, so the order decides how soon a report shows activity
(cheap engines first) and how soon its score stops moving (the engines the fit
weighs before the ones it gives no weight).
"""

import random

import pytest

from app.analyzer import _CHEAP_ENGINES, _engines, engine_order
from app.calibration import _CALIBRATION, calibrated_score, scoring_engines
from tests.samples import AI_TEXT, HUMAN_TEXT

SPANISH = (
    "El consejo municipal aprobó el plan después de varios meses de debate, y los "
    "vecinos dijeron que nadie les había preguntado nada sobre esa decisión, que se "
    "tomó muy deprisa y sin avisarles con tiempo, aunque afectaba a todo el barrio."
)


@pytest.mark.parametrize("text", [AI_TEXT, SPANISH], ids=["english", "spanish"])
def test_cheap_then_scoring_then_the_rest(text):
    order = [key for key, _ in engine_order(text)]
    scoring = scoring_engines(text)
    ranks = [0 if k in _CHEAP_ENGINES else 1 if k in scoring else 2 for k in order]
    assert ranks == sorted(ranks)
    assert sorted(order) == sorted(key for key, _ in _engines)


def test_scoring_engines_are_the_weighted_ones_for_the_language():
    english = {k for k, w in _CALIBRATION["english"]["weights"].items() if w > 0}
    multilingual = {
        k for k, w in _CALIBRATION["multilingual"]["weights"].items() if w > 0
    }
    assert scoring_engines(AI_TEXT) == english
    assert scoring_engines(SPANISH) == multilingual
    assert scoring_engines(AI_TEXT) <= {key for key, _ in _engines}


@pytest.mark.parametrize("text", [AI_TEXT, HUMAN_TEXT, SPANISH])
def test_engines_outside_the_scoring_set_do_not_move_the_score(text):
    """What score_final promises: once the scoring engines are in, the rest of
    the engines can report anything and the overall score stays the same."""
    rng = random.Random(0)
    scoring = scoring_engines(text)
    base = {key: rng.random() for key in scoring}
    expected, _, _ = calibrated_score(base, text)
    for _ in range(5):
        others = {key: rng.random() for key, _ in _engines if key not in scoring}
        score, _, _ = calibrated_score({**base, **others}, text)
        assert score == expected


class _Fake:
    """Stands in for an engine: a fixed score, no model."""

    def __init__(self, name, score):
        self.name, self._score = name, score

    def analyze(self, text):
        from app.schemas import EngineResult, score_to_engine_verdict

        return EngineResult(
            engine_name=self.name,
            score=self._score,
            verdict=score_to_engine_verdict(self._score),
            details="",
            description="",
        )


def test_the_stream_says_when_the_score_is_final(monkeypatch):
    """Every event carries score_final; it turns true with the last scoring
    engine and the overall score never changes after that."""
    import asyncio

    import app.analyzer as analyzer
    from app.database import init_database

    rng = random.Random(1)
    fakes = [(key, _Fake(key, rng.random())) for key, _ in _engines]
    monkeypatch.setattr(analyzer, "_engines", fakes)
    monkeypatch.setattr(analyzer, "CACHE_ENABLED", False)
    scoring = scoring_engines(AI_TEXT)

    async def run():
        await init_database()
        report_id, cached = await analyzer.start_analysis(AI_TEXT, lane="short")
        assert not cached
        events, started = [], []
        async for key, result, report, final, rng in analyzer.stream_results(report_id):
            if result is None:
                started.append(key)
                continue
            events.append((key, report.overall_score, final, rng))
        await analyzer.wait_until_done(report_id)
        return events, started

    events, started = asyncio.run(run())
    assert len(events) == len(fakes)
    # every model engine says it started; the cheap ones just report
    assert sorted(started) == sorted(k for k, _ in fakes if k not in _CHEAP_ENGINES)
    first_final = next(i for i, (_, _, final, _) in enumerate(events) if final)
    assert {key for key, _, _, _ in events[: first_final + 1]} >= scoring
    assert all(final for _, _, final, _ in events[first_final:])
    assert len({score for _, score, _, _ in events[first_final:]}) == 1
    # the range always holds the final score and only ever narrows
    final_score = events[-1][1]
    previous = (0.0, 100.0)
    for _, _, _, (low, high) in events:
        assert low - 0.05 <= final_score <= high + 0.05
        assert low >= previous[0] - 0.05 and high <= previous[1] + 0.05
        previous = (low, high)
    for _, score, _, (low, high) in events[first_final:]:
        assert low == high == score


def test_the_slowest_model_starts_first_within_its_group():
    from app.analyzer import _ENGINE_COST

    order = [key for key, _ in engine_order(AI_TEXT)]
    scoring = scoring_engines(AI_TEXT)
    weighted_models = [k for k in order if k in scoring and k not in _CHEAP_ENGINES]
    costs = [_ENGINE_COST.get(k, 1) for k in weighted_models]
    assert costs == sorted(costs, reverse=True)
    assert weighted_models[0] == "classifier_desklib"


@pytest.mark.parametrize("text", [AI_TEXT, HUMAN_TEXT, SPANISH])
def test_score_range_brackets_every_possible_outcome(text):
    """Whatever the missing scoring engines report, the score lands inside the
    range given before they reported."""
    from app.calibration import score_range

    rng = random.Random(2)
    scoring = sorted(scoring_engines(text))
    for _ in range(30):
        known = {
            k: rng.random() for k in rng.sample(scoring, rng.randint(0, len(scoring)))
        }
        low, high = score_range(known, text)
        assert low <= high
        for _ in range(10):
            full = {**known, **{k: rng.random() for k in scoring if k not in known}}
            score, _, _ = calibrated_score(full, text)
            assert low - 1e-9 <= score <= high + 1e-9
    everything = {k: rng.random() for k in scoring}
    low, high = score_range(everything, text)
    assert low == high == calibrated_score(everything, text)[0]
