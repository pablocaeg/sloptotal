"""A failed write on a thread-local connection must not leave its transaction open.

The connection outlives the write, so an open transaction keeps an old WAL
snapshot and every later write on that thread fails with "database is locked".
"""

import asyncio
import sqlite3
import uuid

import pytest

from app.database import (
    create_report,
    get_sync_connection,
    init_database,
    insert_engine_result_sync,
    update_report_score_sync,
)


@pytest.fixture(scope="module", autouse=True)
def db():
    asyncio.run(init_database())


def test_failed_insert_does_not_leave_a_transaction_open():
    # No such report: the foreign key fails after the implicit BEGIN.
    with pytest.raises(sqlite3.IntegrityError):
        insert_engine_result_sync("missing", "gltr", "GLTR", 0.5, "clean", "", "")
    assert not get_sync_connection().in_transaction


def test_writes_still_work_after_a_failed_one():
    report_id = uuid.uuid4().hex[:12]
    asyncio.run(
        create_report(report_id, uuid.uuid4().hex, "text", "s", "Some text.", 50, 1)
    )
    with pytest.raises(sqlite3.IntegrityError):
        insert_engine_result_sync("missing", "gltr", "GLTR", 0.5, "clean", "", "")

    # Another connection commits, so a stale snapshot could no longer write.
    asyncio.run(
        create_report(uuid.uuid4().hex[:12], uuid.uuid4().hex, "text", "s", "x", 1, 1)
    )
    insert_engine_result_sync(report_id, "gltr", "GLTR", 0.5, "clean", "", "")
    update_report_score_sync(report_id, 50.0, "Suspicious", 1, "test")
    row = (
        get_sync_connection()
        .execute("SELECT overall_verdict FROM reports WHERE id = ?", (report_id,))
        .fetchone()
    )
    assert row["overall_verdict"] == "Suspicious"
