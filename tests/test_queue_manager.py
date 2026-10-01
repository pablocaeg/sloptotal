import asyncio
import uuid

from app.database import create_report, get_db, init_database
from app.queue_manager import QueueManager


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


def analysis(done: asyncio.Event, report_id: str):
    async def execute(_payload):
        return {"report_id": report_id, "_hold": done.wait()}

    return execute


async def started_manager(slots: int = 1) -> QueueManager:
    manager = QueueManager(max_snippet=1, max_quick=1, max_full=slots)
    await manager.start()
    return manager


async def test_a_slot_stays_taken_until_the_analysis_finishes():
    manager = await started_manager()
    first_done = asyncio.Event()
    first = await manager.submit("full", {}, "a", analysis(first_done, "r1"))
    assert first == {"status": "completed", "result": {"report_id": "r1"}}

    second = await manager.submit("full", {}, "b", analysis(asyncio.Event(), "r2"))
    assert second["status"] == "queued"
    assert second["position"] == 1 and second["ahead"] == 0

    first_done.set()
    await settle()
    status = manager.get_ticket_status(second["ticket_id"])
    assert status == {"status": "completed", "result": {"report_id": "r2"}}
    await manager.stop()


async def test_positions_move_up_as_the_line_moves():
    manager = await started_manager()
    releases = [asyncio.Event() for _ in range(4)]
    await manager.submit("full", {}, "a", analysis(releases[0], "r0"))
    tickets = []
    for i in range(1, 4):
        resp = await manager.submit("full", {}, f"h{i}", analysis(releases[i], f"r{i}"))
        tickets.append(resp["ticket_id"])
    await settle()
    assert [manager.get_ticket_status(t)["position"] for t in tickets] == [1, 2, 3]

    releases[0].set()
    await settle()
    assert manager.get_ticket_status(tickets[0])["status"] == "completed"
    assert [manager.get_ticket_status(t)["position"] for t in tickets[1:]] == [1, 2]
    await manager.stop()


async def test_a_new_request_does_not_jump_the_line():
    manager = await started_manager()
    first_done = asyncio.Event()
    await manager.submit("full", {}, "a", analysis(first_done, "r1"))
    waiting = await manager.submit("full", {}, "b", analysis(asyncio.Event(), "r2"))
    newcomer = await manager.submit("full", {}, "c", analysis(asyncio.Event(), "r3"))
    assert newcomer["status"] == "queued" and newcomer["position"] == 2
    assert manager.get_ticket_status(waiting["ticket_id"])["position"] == 1
    await manager.stop()


async def test_a_failed_hold_still_frees_the_slot():
    manager = await started_manager()

    async def broken_hold():
        raise RuntimeError("engine crashed")

    async def execute(_payload):
        return {"report_id": "r1", "_hold": broken_hold()}

    await manager.submit("full", {}, "a", execute)
    await settle()
    after = await manager.submit("full", {}, "b", analysis(asyncio.Event(), "r2"))
    assert after["status"] == "completed"
    await manager.stop()


async def test_work_without_a_hold_frees_the_slot_immediately():
    manager = await started_manager()

    async def quick(_payload):
        return {"score": 1}

    assert (await manager.submit("full", {}, "a", quick))["status"] == "completed"
    assert (await manager.submit("full", {}, "b", quick))["status"] == "completed"
    await manager.stop()


async def test_an_analysis_nobody_watches_is_still_marked_complete():
    from app import analyzer

    await init_database()
    report_id = uuid.uuid4().hex[:12]
    await create_report(report_id, uuid.uuid4().hex, "text", "s", "text", 10, 23)
    analyzer._done_events[report_id] = asyncio.Event()
    analyzer._pending[report_id] = asyncio.Queue()
    analyzer._result_counts[report_id] = 23

    waiter = asyncio.create_task(analyzer.wait_until_done(report_id))
    await analyzer._finish_analysis(report_id)
    await asyncio.wait_for(waiter, timeout=2)

    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT completed_at FROM reports WHERE id = ?", (report_id,)
            )
        ).fetchone()
    assert row["completed_at"] is not None
    assert report_id not in analyzer._pending
