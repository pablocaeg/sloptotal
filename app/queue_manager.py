"""Async queue manager that sits above the semaphore layer.

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

    def __init__(self, max_snippet: int, max_quick: int, max_full: int):
        self._capacities: dict[str, EndpointCapacity] = {
            "snippet": EndpointCapacity(max_concurrent=max_snippet, max_queue=50),
            "quick": EndpointCapacity(max_concurrent=max_quick, max_queue=50),
            "full": EndpointCapacity(max_concurrent=max_full, max_queue=20),
        }

        # asyncio.PriorityQueue per endpoint
        self._queues: dict[str, asyncio.PriorityQueue] = {}

        # ticket_id -> _QueueItem  (pending items)
        self._tickets: dict[str, _QueueItem] = {}

        # ticket_id -> {"result": ..., "expires": monotonic timestamp}
        self._results: dict[str, dict] = {}

        # text_hash -> ticket_id  (dedup: identical payloads piggyback)
        self._dedup: dict[str, str] = {}

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

        # --- Immediate execution if capacity is free ---
        if cap.has_capacity():
            cap.active += 1
            start = time.monotonic()
            try:
                result = await execute_fn(payload)
            except Exception as e:
                log.error("Queue execute error (%s): %s", endpoint, e)
                return {"status": "error", "error": str(e)}
            finally:
                elapsed = time.monotonic() - start
                cap.active -= 1
                cap.record_latency(elapsed)
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

            position = cap.queue_size
            return {
                "status": "queued",
                "ticket_id": ticket_id,
                "position": position,
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
            # Find which endpoint this belongs to
            for ep_name, cap in self._capacities.items():
                position = self._position_of(ep_name, ticket_id)
                if position > 0:
                    return {
                        "status": "queued",
                        "position": position,
                        "estimated_wait_ms": cap.estimated_wait_ms(position),
                    }
            # In tickets dict but not found in any queue — being processed
            return {"status": "processing"}

        return None

    def queue_status(self) -> dict:
        """Overall capacity info for all endpoints."""
        return {name: cap.status_dict() for name, cap in self._capacities.items()}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _position_of(self, endpoint: str, ticket_id: str) -> int:
        """Approximate position of a ticket in its queue (1-based). 0 if not found."""
        q = self._queues.get(endpoint)
        if not q:
            return 0
        # PriorityQueue._queue is the underlying heap list
        pos = 1
        for _pri, item in list(q._queue):
            if item is not None and item.ticket_id == ticket_id:
                return pos
            pos += 1
        return 0

    async def _worker(self, endpoint: str, q: asyncio.PriorityQueue) -> None:
        """Pull items from the queue when capacity frees up, execute them."""
        cap = self._capacities[endpoint]

        while self._running:
            try:
                _priority, item = await q.get()
            except asyncio.CancelledError:
                return

            if item is None:  # sentinel
                return

            cap.queue_size = max(0, cap.queue_size - 1)
            cap.active += 1
            start = time.monotonic()

            try:
                result = await item.execute_fn(item.payload)
                # Store result for polling
                self._results[item.ticket_id] = {
                    "result": result,
                    "expires": time.monotonic() + RESULT_TTL,
                }
                # Resolve the future (in case anyone is awaiting it directly)
                if not item.future.done():
                    item.future.set_result(result)
            except Exception as e:
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
                elapsed = time.monotonic() - start
                cap.active -= 1
                cap.record_latency(elapsed)
                # Cleanup ticket tracking
                self._tickets.pop(item.ticket_id, None)
                # Remove dedup entry (find by value)
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
