"""Fast mode: half the windows, its own cache tag, and only when asked for."""

import asyncio
import uuid

from app import analyzer
from app.analyzer import FAST_TAG
from app.calibration import CALIBRATION_VERSION
from app.database import (
    create_report,
    init_database,
    mark_report_complete,
    update_report_score,
)
from app.engines.base import (
    LARGE_MODEL_MAX_WINDOWS,
    MAX_WINDOWS,
    fast_windows,
    window_starts,
)
from app.schemas import WebAnalyzeRequest


def test_fast_windows_halves_every_cap_and_restores_it():
    long = 50_000
    assert len(window_starts(long, 510, 256)) == MAX_WINDOWS
    with fast_windows():
        assert len(window_starts(long, 510, 256)) == MAX_WINDOWS // 2
        assert (
            len(window_starts(long, 510, 256, LARGE_MODEL_MAX_WINDOWS))
            == LARGE_MODEL_MAX_WINDOWS // 2
        )
        assert len(window_starts(long, 510, 256, 3)) == 2
    assert len(window_starts(long, 510, 256)) == MAX_WINDOWS


def test_fast_windows_leaves_short_texts_alone():
    with fast_windows():
        assert window_starts(600, 510, 256) == [0, 256, 512]


def test_fast_windows_off_is_a_no_op():
    with fast_windows(False):
        assert len(window_starts(50_000, 510, 256)) == MAX_WINDOWS


def test_web_requests_are_full_unless_they_ask():
    assert WebAnalyzeRequest(text="x").fast is False
    assert WebAnalyzeRequest(text="x", fast=True).fast is True


def _stored(tag: str) -> tuple[str, str]:
    report_id, text = uuid.uuid4().hex[:12], f"Cached text {uuid.uuid4().hex}. " * 20
    from app.cache import compute_text_hash

    async def build():
        await init_database()
        await create_report(
            report_id,
            compute_text_hash(analyzer.fit_to_limit(text)),
            "text",
            "s",
            text,
            60,
            23,
        )
        await update_report_score(report_id, 40.0, "Low risk", 0, tag)
        await mark_report_complete(report_id)

    asyncio.run(build())
    return report_id, text


def test_a_fast_report_is_never_served_to_a_full_request(monkeypatch):
    monkeypatch.setattr(analyzer, "CACHE_ENABLED", True)
    fast_id, text = _stored(FAST_TAG)
    rid, cached = asyncio.run(analyzer.start_analysis(text, fast=True))
    assert (rid, cached) == (fast_id, True)
    started = []
    monkeypatch.setattr(
        analyzer, "create_report", lambda **kw: started.append(kw) or _raise()
    )
    try:
        asyncio.run(analyzer.start_analysis(text))
    except RuntimeError:
        pass
    assert started, "a full request must start its own analysis"


def test_a_full_report_is_good_enough_for_a_fast_request(monkeypatch):
    monkeypatch.setattr(analyzer, "CACHE_ENABLED", True)
    full_id, text = _stored(CALIBRATION_VERSION)
    assert asyncio.run(analyzer.start_analysis(text, fast=True)) == (full_id, True)


def _raise():
    raise RuntimeError("stop before running engines")
