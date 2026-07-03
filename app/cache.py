"""Text hashing utilities for cache lookup."""

import hashlib
import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize text for consistent hashing.

    - Lowercase
    - Unicode NFKC normalization
    - Collapse whitespace to single spaces
    - Strip leading/trailing whitespace
    """
    # Unicode normalize
    text = unicodedata.normalize("NFKC", text)
    # Lowercase
    text = text.lower()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    # Strip
    text = text.strip()
    return text


def compute_text_hash(text: str) -> str:
    """Compute SHA-256 hash of normalized text."""
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


_STALE_FAILURE_MARKERS = (
    "model loading failed",
    "engine error:",
)


def is_cacheable_report(report) -> bool:
    """Return False when a stored report contains engine load/runtime failures."""
    for result in report.engine_results:
        details = (result.details or "").lower()
        if any(marker in details for marker in _STALE_FAILURE_MARKERS):
            return False
    return True
