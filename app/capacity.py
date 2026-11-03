"""Endpoint capacity tracking for the queue system."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class EndpointCapacity:
    """Tracks active slots, queue depth, and rolling latency for one endpoint class."""

    max_concurrent: int
    max_queue: int
    active: int = 0
    queue_size: int = 0
    # The estimate before any job has finished (just after a restart)
    default_latency_ms: float = 500.0
    # Rolling window of recent latencies (seconds) for wait-time estimation
    _latencies: deque = field(default_factory=lambda: deque(maxlen=20))
    # monotonic start times of the jobs holding a slot right now
    _starts: list = field(default_factory=list)

    def has_capacity(self) -> bool:
        return self.active < self.max_concurrent

    def has_queue_room(self) -> bool:
        return self.queue_size < self.max_queue

    def record_latency(self, elapsed: float) -> None:
        self._latencies.append(elapsed)

    def avg_latency_ms(self) -> float:
        if not self._latencies:
            return self.default_latency_ms
        return (sum(self._latencies) / len(self._latencies)) * 1000

    def job_started(self, start: float) -> None:
        self._starts.append(start)

    def job_finished(self, start: float) -> None:
        if start in self._starts:
            self._starts.remove(start)

    def estimated_wait_ms(self, position: int, now: float | None = None) -> int:
        """Estimate wait time for a request at *position* in the queue.

        With the running jobs' start times known, the wait is the time until
        the slot this request needs frees up: the jobs that have run longest
        free theirs first. A job past the average is a long one (long texts
        take several times the average), so it is given half of what it has
        run so far, and never less than a quarter of the average.
        """
        avg = self.avg_latency_ms()
        slots = max(self.max_concurrent, 1)
        if now is None or not self._starts:
            batches = max(1, position / slots)
            return int(batches * avg)
        remaining = sorted(
            max(avg - elapsed, 0.5 * elapsed, 0.25 * avg)
            for elapsed in ((now - start) * 1000 for start in self._starts)
        )
        index = max(position, 1) - 1
        rounds, slot = divmod(index, slots)
        first = remaining[slot] if slot < len(remaining) else 0.0
        return int(first + rounds * avg)

    def status_dict(self) -> dict:
        return {
            "active": self.active,
            "max_concurrent": self.max_concurrent,
            "queued": self.queue_size,
            "max_queue": self.max_queue,
            "accepting": self.has_capacity() or self.has_queue_room(),
            "avg_latency_ms": round(self.avg_latency_ms(), 1),
        }
