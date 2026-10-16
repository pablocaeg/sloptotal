"""SlopTotal as an MCP server, so agents can check text and sites for AI generation.

Run with `sloptotal mcp` (stdio). Text is sent to the SlopTotal API, which is
sloptotal.com unless SLOPTOTAL_URL points at your own server.
"""

import asyncio
import logging

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from sloptotal.client import Report, SlopTotal

INSTRUCTIONS = (
    "SlopTotal runs 23 independent AI-text detectors and returns a calibrated 0-100 score "
    "(under 30 clean, 45 and up worth a look, 55 and up likely AI). A score is evidence, not a "
    "verdict: under about 80 words it is a weak signal, and in some languages detection is only "
    "experimental, which each result states. Never present a score as proof that a person used AI."
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

server = MCPServer(
    name="sloptotal", title="SlopTotal AI text detector", instructions=INSTRUCTIONS
)


def _result(report: Report) -> dict:
    caveats = []
    if report.word_count < 80:
        caveats.append("Under 80 words the score is a weak signal.")
    if report.language_support != "supported":
        caveats.append(
            f"Detection in this language ({report.language}) is {report.language_support}."
        )
    return {
        "score": report.score,
        "verdict": report.verdict,
        "word_count": report.word_count,
        "language": report.language,
        "language_support": report.language_support,
        "top_engines": dict(report.top_engines(5)),
        "caveats": caveats,
        "report_url": report.url,
    }


def _analyze(**kwargs) -> dict:
    with SlopTotal() as api:
        return _result(api.analyze(**kwargs))


@server.tool(title="Check text for AI generation", annotations=READ_ONLY)
async def analyze_text(text: str) -> dict:
    """Score a text (at least 50 characters) with 23 AI detectors; returns the score, verdict, caveats and a report link."""
    return await asyncio.to_thread(_analyze, text=text)


@server.tool(title="Check a web page for AI generation", annotations=READ_ONLY)
async def analyze_url(url: str) -> dict:
    """Extract the article at a public URL and score it with 23 AI detectors."""
    return await asyncio.to_thread(_analyze, url=url)


@server.tool(title="Was this site built with an AI app builder?", annotations=READ_ONLY)
async def check_site(url: str) -> dict:
    """Look for fingerprints that Lovable, v0, Bolt, Base44, Replit and similar builders leave in deployed sites."""

    def scan() -> dict:
        with SlopTotal() as api:
            return api.check_site(url)

    return await asyncio.to_thread(scan)


def run() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    server.run("stdio")
