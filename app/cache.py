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
