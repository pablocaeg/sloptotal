from abc import ABC, abstractmethod
from app.schemas import EngineResult

MAX_WINDOWS = 8


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
