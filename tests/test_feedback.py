import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import (
    create_report,
    get_db,
    get_report_by_hash,
    init_database,
    insert_engine_result_sync,
    mark_report_complete,
    purge_expired_reports,
    update_report_score,
)
from app.main import app


@pytest.fixture(scope="module")
def client():
    asyncio.run(init_database())
    return TestClient(app)


def make_report(complete: bool = True) -> str:
    report_id = uuid.uuid4().hex[:12]

    async def build():
        await create_report(
            report_id, uuid.uuid4().hex, "text", "sample", "The text itself.", 120, 2
        )
        insert_engine_result_sync(
            report_id, "gltr", "GLTR", 0.25, "clean", "details", ""
        )
        insert_engine_result_sync(
            report_id, "perplexity", "Perplexity", 0.75, "slop", "details", ""
        )
        await update_report_score(report_id, 64.0, "Likely AI-generated", 1, "test")
        if complete:
            await mark_report_complete(report_id)

    asyncio.run(build())
    return report_id


def query(sql: str, *params):
    async def run():
        async with get_db() as db:
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            await db.commit()
            return rows

    return asyncio.run(run())


def test_feedback_stores_label_and_scores_but_not_text(client):
    report_id = make_report()
    r = client.post(f"/api/report/{report_id}/feedback", json={"label": "human"})
    assert r.status_code == 200 and r.json() == {"status": "saved"}

    [row] = query("SELECT * FROM report_feedback WHERE report_id = ?", report_id)
    assert row["label"] == "human"
    assert row["overall_score"] == 64.0
    assert json.loads(row["engine_scores"]) == {"GLTR": 0.25, "Perplexity": 0.75}
    assert row["word_count"] == 120 and row["source_type"] == "text"
    assert "The text itself." not in " ".join(str(v) for v in dict(row).values())


def test_a_second_answer_replaces_the_first(client):
    report_id = make_report()
    client.post(f"/api/report/{report_id}/feedback", json={"label": "human"})
    client.post(f"/api/report/{report_id}/feedback", json={"label": "mixed"})
    rows = query("SELECT label FROM report_feedback WHERE report_id = ?", report_id)
    assert [r["label"] for r in rows] == ["mixed"]


@pytest.mark.parametrize("label", ["robot", "", "HUMAN"])
def test_unknown_labels_are_rejected(client, label):
    report_id = make_report()
    assert (
        client.post(
            f"/api/report/{report_id}/feedback", json={"label": label}
        ).status_code
        == 422
    )


def test_unknown_report_is_404(client):
    assert (
        client.post(
            "/api/report/abc123def456/feedback", json={"label": "ai"}
        ).status_code
        == 404
    )


def test_invalid_report_id_is_400(client):
    assert client.post(
        "/api/report/not-valid!/feedback", json={"label": "ai"}
    ).status_code in (400, 404)


def test_report_still_scanning_is_409(client):
    report_id = make_report(complete=False)
    assert (
        client.post(
            f"/api/report/{report_id}/feedback", json={"label": "ai"}
        ).status_code
        == 409
    )


def test_feedback_outlives_the_report_retention_window(client):
    report_id = make_report()
    client.post(f"/api/report/{report_id}/feedback", json={"label": "ai"})
    query(
        "UPDATE reports SET created_at = datetime('now', '-40 days') WHERE id = ?",
        report_id,
    )
    asyncio.run(purge_expired_reports(30))
    assert query("SELECT id FROM reports WHERE id = ?", report_id) == []
    assert (
        len(query("SELECT label FROM report_feedback WHERE report_id = ?", report_id))
        == 1
    )


def test_scan_log_follows_the_retention_window(client):
    query(
        "INSERT INTO scan_log (scan_type, text_excerpt, created_at) VALUES ('snippet', 'old text', datetime('now', '-40 days'))"
    )
    query(
        "INSERT INTO scan_log (scan_type, text_excerpt) VALUES ('snippet', 'new text')"
    )
    asyncio.run(purge_expired_reports(30))
    excerpts = [r["text_excerpt"] for r in query("SELECT text_excerpt FROM scan_log")]
    assert "old text" not in excerpts and "new text" in excerpts


def test_a_cached_report_is_reused_only_under_the_calibration_that_scored_it(client):
    text_hash = uuid.uuid4().hex + uuid.uuid4().hex
    report_id = uuid.uuid4().hex[:12]

    async def build_and_look_up():
        await create_report(report_id, text_hash, "text", "sample", "Text.", 120, 1)
        await update_report_score(report_id, 64.0, "Likely AI-generated", 1, "old")
        await mark_report_complete(report_id)
        return (
            await get_report_by_hash(text_hash, "old"),
            await get_report_by_hash(text_hash, "new"),
        )

    same, changed = asyncio.run(build_and_look_up())

    assert same.id == report_id
    assert changed is None
