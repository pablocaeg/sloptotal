import threading
from abc import ABC, abstractmethod
from collections import deque
from typing import Callable

from app.schemas import EngineResult

MAX_WINDOWS = 8
# Desklib, ReMoDetect and SuperAnnotate are the critical path of a full
# analysis. Side-by-side windows, at most 4, halve their time on long texts and
# moved 5 of 190 verdicts (benchmarks/perf: large_models.py, retime.py).
LARGE_MODEL_MAX_WINDOWS = 4


def window_starts(
    n_tokens: int, window: int, stride: int, max_windows: int = MAX_WINDOWS
) -> list[int]:
    """Start offsets of the sliding windows a classifier scores over a long text.

    Texts that need up to max_windows windows get every one of them. Longer
    texts get max_windows windows spread evenly from the start to the end, so
    one very long paste cannot hold a large model for minutes while other
    analyses wait for it.
    """
    starts = list(range(0, n_tokens, stride))
    if len(starts) <= max_windows:
        return starts
    last = max(0, n_tokens - window)
    return [round(i * last / (max_windows - 1)) for i in range(max_windows)]


class FairLock:
    """A lock handed to waiting threads in arrival order.

    threading.Lock makes no such promise: a thread scoring a long text, which
    releases and retakes the lock between windows, can win it back again and
    again while a short text waits.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._waiters: deque[threading.Event] = deque()
        self._held = False

    def __enter__(self) -> "FairLock":
        with self._guard:
            if not self._held and not self._waiters:
                self._held = True
                return self
            turn = threading.Event()
            self._waiters.append(turn)
        turn.wait()
        return self

    def __exit__(self, *exc) -> None:
        with self._guard:
            if self._waiters:
                self._waiters.popleft().set()
            else:
                self._held = False


def score_in_windows(
    text: str,
    tokenizer,
    score_chunk: Callable[[str], float],
    lock: FairLock,
    window: int = 510,
    stride: int = 256,
    max_windows: int = MAX_WINDOWS,
) -> float:
    """Mean score of a classifier over the windows of a text.

    The model's lock is taken one window at a time, so a short text waits for
    at most one window of a long one, not for the whole text.
    """
    with lock:
        tokens = tokenizer.encode(text, add_special_tokens=False)
    if len(tokens) <= window:
        with lock:
            return score_chunk(text)
    scores = []
    for start in window_starts(len(tokens), window, stride, max_windows):
        ids = tokens[start : start + window]
        if len(ids) < 20:
            break
        with lock:
            scores.append(score_chunk(tokenizer.decode(ids, skip_special_tokens=True)))
    return sum(scores) / len(scores) if scores else 0.0


class BaseEngine(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def code(self) -> str:
        """Short 2-letter code for display (e.g. 'FS', 'TM')."""
        return self.name[:2].upper()

    @property
    def engine_type(self) -> str:
        """Category: 'neural', 'statistical', 'linguistic', 'embedding', 'classifier'."""
        return "neural"

    @property
    def url(self) -> str:
        """External link (HuggingFace, arXiv, etc). Empty string if none."""
        return ""

    @abstractmethod
    def analyze(self, text: str) -> EngineResult: ...
