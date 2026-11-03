from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

EXAMPLE_URL = "https://example.com"
EXAMPLE_TEXT = (
    "The rapid spread of large language models has made it increasingly "
    "difficult to tell whether a piece of writing was produced by a person or "
    "by a machine. Automated detectors attempt to close that gap by measuring "
    "perplexity, burstiness, and other statistical fingerprints that tend to "
    "differ between human and generated prose. No single signal is reliable on "
    "its own, so modern systems combine many weak indicators into a single "
    "calibrated score. The result is a useful tool rather than a verdict, and "
    "it should always be read alongside context, provenance, and the plain "
    "judgement of a careful human reader."
)


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


class FeedbackRequest(BaseModel):
    label: Literal["human", "ai", "mixed", "unsure"]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"label": "human"},
            ]
        }
    }


class AnalyzeRequest(BaseModel):
    url: str | None = None
    text: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"text": EXAMPLE_TEXT},
            ]
        }
    }


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
    input_chars: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @computed_field
    @property
    def language(self) -> str:
        """Detected language of the analysed text, or "other"."""
        from app.language import detect_language

        return detect_language(self.text_excerpt)

    @computed_field
    @property
    def language_support(self) -> str:
        """supported, experimental or unsupported: how far the score is trusted in this language."""
        from app.calibration import language_support

        return language_support(self.language)


def score_to_verdict_str(score: float) -> str:
    """Map a 0-100 score to its verdict band.

    Boundaries live in config.py and are derived from measured score
    distributions. This function used to hardcode its own copy (20/40/60/80)
    while config.SCORE_* went entirely unread, so the two could drift apart
    without anything failing.

    Imported inside the function because config imports nothing from schemas but
    analyzer imports both; a module-level import here would make the dependency
    direction between them harder to reason about.
    """
    from app.config import (
        SCORE_CLEAN,
        SCORE_LIKELY_AI,
        SCORE_LOW_RISK,
        SCORE_SUSPICIOUS,
    )

    if score <= SCORE_CLEAN:
        return "Clean — likely human-written"
    elif score <= SCORE_LOW_RISK:
        return "Low risk"
    elif score <= SCORE_SUSPICIOUS:
        return "Suspicious"
    elif score <= SCORE_LIKELY_AI:
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
    # Half as many windows per classifier on long texts: faster, a little less
    # accurate on texts that change partway through. Off unless asked for.
    fast: bool = False

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"text": EXAMPLE_TEXT},
            ]
        }
    }


class SnippetItem(BaseModel):
    id: str
    text: str
    url: str = ""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"id": "snippet-1", "text": EXAMPLE_TEXT, "url": EXAMPLE_URL},
            ]
        }
    }


class SnippetBatchRequest(BaseModel):
    snippets: list[SnippetItem]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "snippets": [
                        {
                            "id": "snippet-1",
                            "text": EXAMPLE_TEXT,
                            "url": EXAMPLE_URL,
                        }
                    ]
                }
            ]
        }
    }


class SiteScanRequest(BaseModel):
    url: str = ""
    include_text: bool = True

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"url": EXAMPLE_URL, "include_text": True},
            ]
        }
    }


class BatchUrlRequest(BaseModel):
    urls: list[str]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"urls": [EXAMPLE_URL, "https://example.org"]},
            ]
        }
    }


class UrlScanItem(BaseModel):
    id: str
    url: str
    dom_features: dict | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"id": "page-1", "url": EXAMPLE_URL},
            ]
        }
    }


class UrlScanRequest(BaseModel):
    urls: list[UrlScanItem]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"urls": [{"id": "page-1", "url": EXAMPLE_URL}]},
            ]
        }
    }
