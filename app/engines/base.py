from abc import ABC, abstractmethod
from app.schemas import EngineResult


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
