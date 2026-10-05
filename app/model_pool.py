"""Thread-safe pool of model replicas for concurrent inference."""

import logging
import queue
import threading
from contextlib import contextmanager
from typing import Any, Callable

log = logging.getLogger("sloptotal.model_pool")

# Every from_pretrained() call in the process must hold this lock. transformers
# loading is not thread-safe across models: two loads running at once (the
# startup preloader and a first request, say) can leave GPT-2's tied lm_head
# randomly initialised, which showed up as DistilGPT-2 perplexities of 50257
# and 1e15 and pinned Binoculars at 1.0. Reentrant so a loader may call another.
LOAD_LOCK = threading.RLock()


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
        self._init_lock = threading.Lock()
        self._ready = threading.Event()

    def initialize(self) -> None:
        """Load all replicas. Safe to call more than once and from many threads.

        Callers that arrive while another thread is loading block on the lock
        until it finishes, however long the first-run model download takes. A
        failed load raises here and is retried by the next caller.
        """
        with self._init_lock:
            if self._ready.is_set():
                return
            self._load_all()
            self._ready.set()

    def _load_all(self) -> None:
        # Drop replicas from an earlier, partly failed attempt.
        while not self._pool.empty():
            self._pool.get_nowait()
        for i in range(self._pool_size):
            try:
                with LOAD_LOCK:
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
        """Yield a (model, tokenizer) pair, returning it to the pool on exit.

        `timeout` bounds the wait for a free replica under load. It does not
        apply to the first load: until the pool is ready, this waits for (or
        performs) initialisation instead of failing after `timeout` seconds
        while weights are still downloading.
        """
        if not self._ready.is_set():
            self.initialize()
        try:
            replica = self._pool.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError(
                f"ModelPool[{self._name}] timed out waiting for a replica "
                f"after {timeout}s"
            ) from exc
        try:
            yield replica
        finally:
            self._pool.put_nowait(replica)

    @property
    def size(self) -> int:
        return self._pool_size
