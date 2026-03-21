from dataclasses import dataclass

import httpx
import trafilatura
from bs4 import BeautifulSoup

# Models only process ~750-1024 tokens. Extracting more is wasted work.
MAX_WORDS = 1000

# Heuristic engines are pure regex — benefit from more text than ML models need
MAX_ML_CHARS = 500
MAX_HEURISTIC_CHARS = 4000


@dataclass
class PageContent:
    """Split text for ML (short) vs heuristic (long) analysis pipelines."""

    ml_text: str  # First 500ch — Fakespot-reliable truncation
    heuristic_text: str  # First 4000ch — regex engines benefit from more text
    full_text: str  # Full extracted text
    char_count: int
    word_count: int
    html_features: dict | None = None  # HTML structural features (Phase B)


def extract_html_features(html: str) -> dict:
    """Extract structural features from raw HTML before trafilatura strips them.

    Counts lists, headings, heading→list section patterns, tables, bold elements.
    Cost: ~2ms (DOM parse is fast).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Count lists and their items
    lists = soup.find_all(["ul", "ol"])
    list_count = len(lists)
    list_items = sum(len(lst.find_all("li", recursive=False)) for lst in lists)

    # Count headings
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    heading_count = len(headings)

    # Count heading → list section patterns (heading followed by a list within 3 siblings)
    heading_list_sections = 0
    for heading in headings:
        sibling = heading.find_next_sibling()
        steps = 0
        while sibling and steps < 3:
            if sibling.name in ("ul", "ol"):
                heading_list_sections += 1
                break
            sibling = sibling.find_next_sibling()
            steps += 1

    # Count tables
    tables = len(soup.find_all("table"))

    # Count bold/strong elements
    bold_count = len(soup.find_all(["b", "strong"]))

    # Count paragraphs
    paragraph_count = len(soup.find_all("p"))

    # Count links within <nav> elements (hub/index signal)
    nav_links = 0
    for nav in soup.find_all("nav"):
        nav_links += len(nav.find_all("a", href=True))

    # Count forms (landing page signal)
    form_count = len(soup.find_all("form"))

    # Count code blocks (reference/docs signal)
    code_blocks = len(soup.find_all(["pre", "code"]))

    return {
        "list_count": list_count,
        "list_items": list_items,
        "headings": heading_count,
        "heading_list_sections": heading_list_sections,
        "tables": tables,
        "bold_count": bold_count,
        "paragraph_count": paragraph_count,
        "nav_links": nav_links,
        "form_count": form_count,
        "code_blocks": code_blocks,
    }


async def _fetch_html(url: str) -> str:
    """Fetch raw HTML from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SlopTotal/1.0; +https://sloptotal.com)"
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


def _extract_text_from_html(html: str) -> str:
    """Extract main text content from raw HTML using trafilatura."""
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        no_fallback=True,
    )

    if not text or len(text.strip()) < 50:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )

    if not text or len(text.strip()) < 50:
        raise ValueError("Could not extract meaningful text from the URL.")

    text = text.strip()

    # Cap at MAX_WORDS to avoid wasting compute on huge articles
    words = text.split()
    if len(words) > MAX_WORDS:
        text = " ".join(words[:MAX_WORDS])

    return text


async def extract_text_with_metadata(url: str) -> PageContent:
    """Fetch URL, extract text + HTML features, return split content.

    HTML features are extracted from raw HTML before trafilatura strips structure.
    """
    html = await _fetch_html(url)
    html_features = extract_html_features(html)
    full_text = _extract_text_from_html(html)
    return PageContent(
        ml_text=full_text[:MAX_ML_CHARS],
        heuristic_text=full_text[:MAX_HEURISTIC_CHARS],
        full_text=full_text,
        char_count=len(full_text),
        word_count=len(full_text.split()),
        html_features=html_features,
    )


async def extract_text_from_url(url: str) -> str:
    """Fetch a URL and extract its main text content."""
    html = await _fetch_html(url)
    return _extract_text_from_html(html)
