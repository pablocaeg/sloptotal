"""Thread-safe pool of model replicas for concurrent inference."""

import logging
import queue
from contextlib import contextmanager
from typing import Any, Callable

log = logging.getLogger("sloptotal.model_pool")


class ModelPool:
    """A fixed-size pool of (model, tokenizer) pairs backed by queue.Queue.

    queue.Queue.get() blocks when all replicas are checked out, providing
    the same backpressure as a Lock but allowing N concurrent users.
    """

    def __init__(self, load_fn: Callable[[], Any], pool_size: int = 1, name: str = ""):
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size)
        self._load_fn = load_fn
        self._pool_size = pool_size
        self._name = name

    def initialize(self) -> None:
        """Pre-load all replicas (call at startup)."""
        for i in range(self._pool_size):
            try:
                replica = self._load_fn()
                self._pool.put_nowait(replica)
                log.info(
                    f"ModelPool[{self._name}] replica {i + 1}/{self._pool_size} loaded"
                )
            except Exception:
                log.exception(f"ModelPool[{self._name}] failed to load replica {i + 1}")
                raise

    @contextmanager
    def acquire(self, timeout: float = 30.0):
        """Yield a (model, tokenizer) pair, returning it to the pool on exit."""
        try:
            replica = self._pool.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(
                f"ModelPool[{self._name}] timed out waiting for a replica "
                f"after {timeout}s"
            )
        try:
            yield replica
        finally:
            self._pool.put_nowait(replica)

    @property
    def size(self) -> int:
        return self._pool_size
