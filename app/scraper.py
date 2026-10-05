import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.language import count_words

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


# Self-hosters scanning their own intranet can opt out of the private-address
# guard; the public API must never fetch internal or cloud-metadata addresses.
ALLOW_PRIVATE_URLS = os.getenv("SLOPTOTAL_ALLOW_PRIVATE_URLS", "").lower() in (
    "1",
    "true",
    "yes",
)
MAX_HTML_BYTES = 5_000_000


async def _check_public_url(url: str) -> None:
    """Reject non-HTTP schemes and hosts that resolve to private addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only http:// and https:// URLs can be scanned.")
    if ALLOW_PRIVATE_URLS:
        return
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, None, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve {parsed.hostname}.") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if not addr.is_global:
            raise ValueError("That URL points to a private network address.")


async def _fetch(url: str) -> httpx.Response:
    """GET a public URL, re-checking every redirect hop against the guard."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SlopTotal/1.0; +https://sloptotal.com)"
    }

    async def guard(request: httpx.Request) -> None:
        await _check_public_url(str(request.url))

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=15.0,
        max_redirects=5,
        event_hooks={"request": [guard]},
    ) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        if len(response.content) > MAX_HTML_BYTES:
            raise ValueError("Page is too large to scan.")
        return response


async def _fetch_html(url: str) -> str:
    """Fetch raw HTML from a URL."""
    return (await _fetch(url)).text


async def fetch_page(url: str) -> tuple[str, dict[str, str], str]:
    """Fetch a page, returning (html, response headers, final URL after redirects)."""
    response = await _fetch(url)
    return response.text, dict(response.headers), str(response.url)


def _extract_text_from_html(html: str) -> str:
    """Extract main text content from raw HTML using trafilatura."""
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        fast=True,
    )

    if not text or len(text.strip()) < 50:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            fast=False,
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
        word_count=count_words(full_text),
        html_features=html_features,
    )


async def extract_text_from_url(url: str) -> str:
    """Fetch a URL and extract its main text content."""
    html = await _fetch_html(url)
    return _extract_text_from_html(html)
