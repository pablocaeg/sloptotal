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
    # Rolling window of recent latencies (seconds) for wait-time estimation
    _latencies: deque = field(default_factory=lambda: deque(maxlen=20))

    def has_capacity(self) -> bool:
        return self.active < self.max_concurrent

    def has_queue_room(self) -> bool:
        return self.queue_size < self.max_queue

    def record_latency(self, elapsed: float) -> None:
        self._latencies.append(elapsed)

    def avg_latency_ms(self) -> float:
        if not self._latencies:
            return 500.0  # default estimate
        return (sum(self._latencies) / len(self._latencies)) * 1000

    def estimated_wait_ms(self, position: int) -> int:
        """Estimate wait time for a request at *position* in the queue."""
        batches = max(1, position / max(self.max_concurrent, 1))
        return int(batches * self.avg_latency_ms())

    def status_dict(self) -> dict:
        return {
            "active": self.active,
            "max_concurrent": self.max_concurrent,
            "queued": self.queue_size,
            "max_queue": self.max_queue,
            "accepting": self.has_capacity() or self.has_queue_room(),
            "avg_latency_ms": round(self.avg_latency_ms(), 1),
        }
