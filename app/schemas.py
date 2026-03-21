from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from datetime import datetime


class Verdict(str, Enum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    SLOP = "slop"


class EngineResult(BaseModel):
    engine_name: str
    score: float = Field(ge=0.0, le=1.0)
    verdict: Verdict
    details: str
    description: str = ""


class AnalyzeRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None


class AnalysisReport(BaseModel):
    id: str
    source_type: str  # "url" or "text"
    source: str  # URL or first 100 chars of text
    text_excerpt: str
    word_count: int
    engine_results: list[EngineResult]
    overall_score: float = Field(ge=0.0, le=100.0)
    overall_verdict: str
    engines_flagged: int
    engines_total: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


def score_to_verdict_str(score: float) -> str:
    if score <= 20:
        return "Clean — likely human-written"
    elif score <= 40:
        return "Low risk"
    elif score <= 60:
        return "Suspicious"
    elif score <= 80:
        return "Likely AI-generated"
    else:
        return "Slop detected"


def score_to_engine_verdict(score: float) -> Verdict:
    if score < 0.4:
        return Verdict.CLEAN
    elif score < 0.65:
        return Verdict.SUSPICIOUS
    else:
        return Verdict.SLOP


# --- Request models used by route handlers ---


class WebAnalyzeRequest(BaseModel):
    url: str = ""
    text: str = ""


class SnippetItem(BaseModel):
    id: str
    text: str
    url: str = ""


class SnippetBatchRequest(BaseModel):
    snippets: list[SnippetItem]


class BatchUrlRequest(BaseModel):
    urls: list[str]


class UrlScanItem(BaseModel):
    id: str
    url: str
    dom_features: dict | None = None


class UrlScanRequest(BaseModel):
    urls: list[UrlScanItem]
