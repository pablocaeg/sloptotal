"""Async queue manager that sits above the semaphore layer.

Each endpoint has a fixed number of slots. A request takes a slot and keeps it
until its work is finished; for a full analysis that is when every engine has
reported, not when the report id comes back. Waiting requests are served
strictly in arrival order, and a new request never jumps ahead of them.

When the server has capacity the request executes immediately (HTTP 200).
When at capacity the request is queued and the caller gets a ticket (HTTP 202).
Clients poll /api/queue/ticket/{ticket_id} to retrieve results.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable

from app.capacity import EndpointCapacity

log = logging.getLogger("sloptotal.queue")

# Type alias for the async function the queue will call when a slot opens.
ExecuteFn = Callable[..., Awaitable[Any]]

# How long completed results stay in the store (seconds).
RESULT_TTL = 300  # 5 min
CLEANUP_INTERVAL = 60  # seconds


class _QueueItem:
    """One pending request waiting in a queue."""

    __slots__ = (
        "ticket_id",
        "priority",
        "payload",
        "execute_fn",
        "future",
        "enqueued_at",
    )

    def __init__(
        self, ticket_id: str, priority: int, payload: Any, execute_fn: ExecuteFn
    ):
        self.ticket_id = ticket_id
        self.priority = priority
        self.payload = payload
        self.execute_fn = execute_fn
        self.future: asyncio.Future = asyncio.get_running_loop().create_future()
        self.enqueued_at = time.monotonic()

    def __lt__(self, other: _QueueItem) -> bool:
        return self.priority < other.priority


class QueueManager:
    """Manages per-endpoint async queues with capacity tracking."""

    def __init__(
        self, max_snippet: int, max_quick: int, max_full: int, max_short: int = 2
    ):
        self._capacities: dict[str, EndpointCapacity] = {
            "snippet": EndpointCapacity(max_concurrent=max_snippet, max_queue=50),
            "quick": EndpointCapacity(max_concurrent=max_quick, max_queue=50),
            "full": EndpointCapacity(max_concurrent=max_full, max_queue=20),
            "short": EndpointCapacity(max_concurrent=max_short, max_queue=20),
        }

        # asyncio.PriorityQueue per endpoint
        self._queues: dict[str, asyncio.PriorityQueue] = {}

        # ticket_id -> _QueueItem  (pending items)
        self._tickets: dict[str, _QueueItem] = {}

        # ticket_id -> {"result": ..., "expires": monotonic timestamp}
        self._results: dict[str, dict] = {}

        # text_hash -> ticket_id  (dedup: identical payloads piggyback)
        self._dedup: dict[str, str] = {}

        # One semaphore per endpoint: the real concurrency limit.
        self._slots: dict[str, asyncio.Semaphore] = {
            name: asyncio.Semaphore(cap.max_concurrent)
            for name, cap in self._capacities.items()
        }
        # endpoint -> the item a worker has taken off the queue and that is
        # waiting for a slot; it is next in line.
        self._next: dict[str, _QueueItem | None] = {
            name: None for name in self._capacities
        }
        # Background tasks holding slots until long-running work finishes.
        self._holds: set[asyncio.Task] = set()
        # Worker tasks
        self._workers: list[asyncio.Task] = []
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        for name in self._capacities:
            q: asyncio.PriorityQueue = asyncio.PriorityQueue()
            self._queues[name] = q
            task = asyncio.create_task(
                self._worker(name, q), name=f"queue-worker-{name}"
            )
            self._workers.append(task)
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(), name="queue-cleanup"
        )
        log.info(
            "QueueManager started (%s)",
            ", ".join(f"{k}={v.max_concurrent}" for k, v in self._capacities.items()),
        )

    async def stop(self) -> None:
        self._running = False
        # Unblock workers by putting sentinel items
        for q in self._queues.values():
            await q.put((999, None))
        for t in self._workers:
            t.cancel()
        for t in list(self._holds):
            t.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        self._workers.clear()
        log.info("QueueManager stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(
        self,
        endpoint: str,
        payload: Any,
        text_hash: str,
        execute_fn: ExecuteFn,
    ) -> dict:
        """Submit a request.  Returns immediately or queues it.

        Returns dict with:
          {"status": "completed", "result": <result>}      — immediate
          {"status": "queued", "ticket_id": ..., ...}       — queued
          {"status": "rejected", "error": ..., ...}         — queue full
        """
        cap = self._capacities[endpoint]

        # --- Dedup: if identical text is already queued, piggyback ---
        if text_hash and text_hash in self._dedup:
            existing_ticket = self._dedup[text_hash]
            if existing_ticket in self._tickets:
                item = self._tickets[existing_ticket]
                position = self._position_of(endpoint, existing_ticket)
                return {
                    "status": "queued",
                    "ticket_id": existing_ticket,
                    "position": position,
                    "estimated_wait_ms": cap.estimated_wait_ms(position),
                }
            # Also check results store
            if existing_ticket in self._results:
                return {
                    "status": "completed",
                    "result": self._results[existing_ticket]["result"],
                }

        # --- Immediate execution if a slot is free and nobody is waiting ---
        slots = self._slots[endpoint]
        nobody_waiting = self._queues[endpoint].empty() and self._next[endpoint] is None
        if nobody_waiting and not slots.locked():
            await slots.acquire()
            cap.active += 1
            start = time.monotonic()
            try:
                result = await execute_fn(payload)
            except Exception as e:
                self._release(endpoint, start)
                log.error("Queue execute error (%s): %s", endpoint, e)
                return {"status": "error", "error": str(e)}
            result = self._hold_or_release(endpoint, start, result)
            return {"status": "completed", "result": result}

        # --- Enqueue if room ---
        if cap.has_queue_room():
            ticket_id = uuid.uuid4().hex[:16]
            item = _QueueItem(
                ticket_id=ticket_id,
                priority=int(time.monotonic() * 1000),  # FIFO via timestamp
                payload=payload,
                execute_fn=execute_fn,
            )
            self._tickets[ticket_id] = item
            if text_hash:
                self._dedup[text_hash] = ticket_id
            cap.queue_size += 1
            await self._queues[endpoint].put((item.priority, item))

            position = self._position_of(endpoint, ticket_id)
            return {
                "status": "queued",
                "ticket_id": ticket_id,
                "position": position,
                "ahead": position - 1,
                "active": cap.active,
                "estimated_wait_ms": cap.estimated_wait_ms(position),
            }

        # --- Queue full: reject ---
        return {
            "status": "rejected",
            "error": f"Server overloaded — {endpoint} queue full ({cap.max_queue})",
            "retry_after": int(cap.avg_latency_ms() / 1000) + 1,
        }

    def get_ticket_status(self, ticket_id: str) -> dict | None:
        """Check status of a queued/completed ticket.

        Returns:
          {"status": "completed", "result": ...}  — done
          {"status": "queued", "position": N, ...} — still waiting
          None                                     — expired / unknown
        """
        # Check results store first
        if ticket_id in self._results:
            entry = self._results[ticket_id]
            if time.monotonic() < entry["expires"]:
                return {"status": "completed", "result": entry["result"]}
            else:
                del self._results[ticket_id]
                return None

        # Check pending tickets
        if ticket_id in self._tickets:
            for ep_name, cap in self._capacities.items():
                position = self._position_of(ep_name, ticket_id)
                if position > 0:
                    return {
                        "status": "queued",
                        "position": position,
                        "ahead": position - 1,
                        "active": cap.active,
                        "estimated_wait_ms": cap.estimated_wait_ms(position),
                    }
            return {"status": "processing"}

        return None

    def queue_status(self) -> dict:
        """Overall capacity info for all endpoints."""
        return {name: cap.status_dict() for name, cap in self._capacities.items()}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _position_of(self, endpoint: str, ticket_id: str) -> int:
        """Position in line (1 = next to start). 0 if the ticket is not waiting."""
        waiting_first = self._next.get(endpoint)
        if waiting_first is not None and waiting_first.ticket_id == ticket_id:
            return 1
        offset = 1 if waiting_first is not None else 0
        q = self._queues.get(endpoint)
        if not q:
            return 0
        ordered = sorted(item for _pri, item in list(q._queue) if item is not None)
        for index, item in enumerate(ordered, start=1):
            if item.ticket_id == ticket_id:
                return index + offset
        return 0

    def _release(self, endpoint: str, start: float) -> None:
        cap = self._capacities[endpoint]
        cap.active = max(0, cap.active - 1)
        cap.record_latency(time.monotonic() - start)
        self._slots[endpoint].release()

    def _hold_or_release(self, endpoint: str, start: float, result: Any) -> Any:
        """Keep the slot while the result's "_hold" awaitable runs, else free it now.

        execute functions for full analyses return the report id straight away
        and a "_hold" awaitable that finishes when every engine has reported.
        """
        hold = result.pop("_hold", None) if isinstance(result, dict) else None
        if hold is None:
            self._release(endpoint, start)
            return result

        hold = asyncio.ensure_future(hold)

        async def keep_slot() -> None:
            try:
                await hold
            except Exception as e:
                log.error("Queue hold error (%s): %s", endpoint, e)
            finally:
                self._release(endpoint, start)

        task = asyncio.create_task(keep_slot())
        for pending in (task, hold):
            self._holds.add(pending)
            pending.add_done_callback(self._holds.discard)
        return result

    async def _worker(self, endpoint: str, q: asyncio.PriorityQueue) -> None:
        """Start queued items one by one, in arrival order, as slots free up."""
        cap = self._capacities[endpoint]
        slots = self._slots[endpoint]

        while self._running:
            try:
                _priority, item = await q.get()
            except asyncio.CancelledError:
                return

            if item is None:  # sentinel
                return

            cap.queue_size = max(0, cap.queue_size - 1)
            self._next[endpoint] = item
            try:
                await slots.acquire()
            except asyncio.CancelledError:
                return
            finally:
                self._next[endpoint] = None
            cap.active += 1
            start = time.monotonic()

            try:
                result = await item.execute_fn(item.payload)
                result = self._hold_or_release(endpoint, start, result)
                self._results[item.ticket_id] = {
                    "result": result,
                    "expires": time.monotonic() + RESULT_TTL,
                }
                if not item.future.done():
                    item.future.set_result(result)
            except Exception as e:
                self._release(endpoint, start)
                log.error(
                    "Queue worker error (%s, ticket=%s): %s",
                    endpoint,
                    item.ticket_id,
                    e,
                )
                error_result = {"error": str(e)}
                self._results[item.ticket_id] = {
                    "result": error_result,
                    "expires": time.monotonic() + RESULT_TTL,
                }
                if not item.future.done():
                    item.future.set_exception(e)
            finally:
                self._tickets.pop(item.ticket_id, None)
                to_remove = [k for k, v in self._dedup.items() if v == item.ticket_id]
                for k in to_remove:
                    del self._dedup[k]

    async def _cleanup_loop(self) -> None:
        """Expire old results periodically."""
        while self._running:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL)
            except asyncio.CancelledError:
                return

            now = time.monotonic()
            expired = [
                tid for tid, entry in self._results.items() if now >= entry["expires"]
            ]
            for tid in expired:
                del self._results[tid]
            if expired:
                log.debug("Cleaned up %d expired queue results", len(expired))
