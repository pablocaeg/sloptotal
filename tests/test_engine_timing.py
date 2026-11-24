"""Each engine result carries the wall time of its analyze() call."""

import asyncio
import time
import uuid

import pytest

from app.analyzer import _run_engine
from app.database import (
    create_report,
    get_report,
    init_database,
    insert_engine_result_sync,
    mark_report_complete,
)
from app.schemas import EngineResult, Verdict


class _SlowEngine:
    def analyze(self, text: str) -> EngineResult:
        time.sleep(0.05)
        return EngineResult(
            engine_name="slow", score=0.5, verdict=Verdict.CLEAN, details="ok"
        )


@pytest.fixture(scope="module", autouse=True)
def db():
    asyncio.run(init_database())


def test_run_engine_records_elapsed_ms():
    result = _run_engine(_SlowEngine(), "some text")
    assert result.elapsed_ms is not None
    assert result.elapsed_ms >= 50


def test_elapsed_ms_is_stored_and_read_back():
    report_id = uuid.uuid4().hex[:12]

    async def go():
        await create_report(
            report_id, uuid.uuid4().hex, "text", "s", "Some text.", 50, 2
        )
        insert_engine_result_sync(
            report_id, "a", "A", 0.5, "clean", "", "", elapsed_ms=123.4
        )
        # Rows written without a timing (older callers) still load.
        insert_engine_result_sync(report_id, "b", "B", 0.5, "clean", "", "")
        await mark_report_complete(report_id)
        return await get_report(report_id)

    report = asyncio.run(go())
    assert [r.elapsed_ms for r in report.engine_results] == [123.4, None]
    assert "elapsed_ms" in report.model_dump()["engine_results"][0]
