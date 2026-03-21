"""Page type classification for URL scans.

Classifies pages as article, hub, landing, reference, or short
so non-article pages show useful info instead of misleading AI scores.
"""

import re


def classify_page_type(
    text: str,
    html_features: dict | None = None,
    char_count: int = 0,
    dom_features: dict | None = None,
) -> dict:
    """Classify a page by type for scoring strategy selection.

    Returns {"type": str, "label": str, "scoreable": bool}

    Classification order (first match wins):
    1. Short — not enough text for reliable analysis
    2. Hub/Index — link directories, search results, category pages
    3. Landing — promotional pages with minimal prose
    4. Reference/Docs — technical documentation, code-heavy pages
    5. Article — default, full scoring
    """
    if char_count == 0:
        char_count = len(text) if text else 0

    hf = html_features or {}
    df = dom_features or {}

    # --- 1. Short: not enough text ---
    if char_count < 200:
        return {"type": "short", "label": "Short page", "scoreable": False}

    word_count = len(text.split()) if text else 0

    # --- 2. Hub/Index: high link density, low prose ---
    nav_links = hf.get("nav_links", 0)
    list_items = hf.get("list_items", 0)
    paragraph_count = hf.get("paragraph_count", 0)

    # DOM features override HTML features when available
    if df:
        paragraph_count = max(paragraph_count, df.get("paragraph_count", 0))

    is_hub = False
    if word_count > 0:
        li_density = list_items / word_count if word_count else 0
        if li_density > 0.5 and paragraph_count < 5:
            is_hub = True
    if nav_links > 20 and paragraph_count < 5:
        is_hub = True
    if is_hub:
        return {"type": "hub", "label": "Hub page", "scoreable": False}

    # --- 3. Landing: low text, high formatting, few paragraphs ---
    bold_count = hf.get("bold_count", 0)
    form_count = hf.get("form_count", 0)
    if char_count < 800 and paragraph_count < 8:
        if bold_count > 5 or form_count > 1:
            return {"type": "landing", "label": "Landing page", "scoreable": False}

    # --- 4. Reference/Docs: code-heavy, technical content ---
    code_blocks = hf.get("code_blocks", 0)

    # Text-based technical markers
    colon_count = text.count(":") if text else 0
    colon_density = colon_count / max(word_count, 1)

    # Code fence markers in extracted text (trafilatura may preserve some)
    code_fence_count = len(re.findall(r"```|~~~", text)) if text else 0

    # Technical pattern: parameter lists, type annotations, API signatures
    tech_patterns = (
        len(
            re.findall(
                r"\b(?:param|returns?|type|default|args?|kwargs?|raises?|str|int|float|bool|None|True|False|dict|list|tuple)\b",
                text,
            )
        )
        if text
        else 0
    )

    is_reference = False
    if code_blocks > 3:
        is_reference = True
    elif colon_density > 0.04 and code_blocks >= 1:
        is_reference = True
    elif tech_patterns > 15 and code_blocks >= 1:
        is_reference = True
    elif code_fence_count >= 4:
        is_reference = True

    if is_reference:
        return {"type": "reference", "label": "Documentation", "scoreable": True}

    # --- 5. Article (default) ---
    return {"type": "article", "label": "Article", "scoreable": True}
