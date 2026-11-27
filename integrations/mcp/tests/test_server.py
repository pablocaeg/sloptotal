"""The MCP tools against a mocked SlopTotal API (no network, no models)."""

import json

import httpx
import pytest
from mcp import Client
from sloptotal_mcp import server

TEXT = "Artificial intelligence has fundamentally transformed the landscape of modern education."

REPORT = {
    "id": "abc123",
    "source_type": "text",
    "source": TEXT[:100],
    "text_excerpt": TEXT,
    "word_count": 11,
    "engine_results": [
        {
            "engine_name": "Fakespot",
            "score": 0.91234567,
            "verdict": "ai",
            "details": "",
            "description": "",
        },
        {
            "engine_name": "Burstiness",
            "score": 0.2,
            "verdict": "human",
            "details": "",
            "description": "",
        },
    ],
    "overall_score": 71.5,
    "overall_verdict": "Likely AI",
    "engines_flagged": 1,
    "engines_total": 2,
    "language": "en",
    "language_support": "supported",
}


class Calls(list):
    """Requests the mock API received, plus its routes."""

    def __init__(self):
        super().__init__()
        self.routes = {}


@pytest.fixture
def api(monkeypatch):
    """Install a mock API; returns the list of requests it received."""
    calls = Calls()
    routes = calls.routes

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        key = (request.method, request.url.path)
        responder = routes[key]
        return responder(request) if callable(responder) else responder

    monkeypatch.setattr(server, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(server, "POLL_SECONDS", 0.0)
    monkeypatch.delenv("SLOPTOTAL_URL", raising=False)
    return calls


async def call(name, args):
    async with Client(server.mcp) as client:
        return await client.call_tool(name, args)


def payload(result):
    assert not result.is_error, result.content
    return result.structured_content


async def test_lists_the_three_tools():
    async with Client(server.mcp) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
    assert tools == {"analyze_text", "analyze_url", "check_website_builder"}


async def test_analyze_text_summarizes_the_report(api):
    api.routes[("POST", "/api/analyze")] = httpx.Response(200, json=REPORT)
    out = payload(await call("analyze_text", {"text": TEXT}))
    assert out["overall_score"] == 71.5
    assert out["overall_verdict"] == "Likely AI"
    assert out["engines"][0] == {"engine": "Fakespot", "score": 0.9123, "verdict": "ai"}
    assert out["report_url"] == "http://localhost:8000/report/abc123"
    assert json.loads(api[0].content) == {"text": TEXT}


async def test_public_api_links_to_the_website_report(api, monkeypatch):
    monkeypatch.setenv("SLOPTOTAL_URL", "https://api.sloptotal.com/")
    api.routes[("POST", "/api/analyze")] = httpx.Response(200, json=REPORT)
    out = payload(await call("analyze_text", {"text": TEXT}))
    assert out["report_url"] == "https://sloptotal.com/report/?id=abc123"
    assert str(api[0].url).startswith("https://api.sloptotal.com/api/analyze")


async def test_docker_host_is_local_and_links_to_localhost(api, monkeypatch):
    monkeypatch.setenv("SLOPTOTAL_URL", "http://host.docker.internal:8000")
    assert server.is_local(server.base_url())
    api.routes[("POST", "/api/analyze")] = httpx.Response(200, json=REPORT)
    out = payload(await call("analyze_text", {"text": TEXT}))
    assert out["report_url"] == "http://localhost:8000/report/abc123"
    assert str(api[0].url).startswith("http://host.docker.internal:8000/api/analyze")


async def test_short_text_is_refused_without_a_request(api):
    result = await call("analyze_text", {"text": "too short"})
    assert result.is_error
    assert "50 characters" in result.content[0].text
    assert api == []


async def test_queue_ticket_is_polled(api):
    api.routes[("POST", "/api/analyze")] = httpx.Response(
        202, json={"status": "queued", "ticket_id": "t1"}
    )
    polls = iter(
        [
            httpx.Response(202, json={"status": "queued", "position": 1}),
            httpx.Response(200, json=REPORT),
        ]
    )
    api.routes[("GET", "/api/queue/ticket/t1")] = lambda r: next(polls)
    out = payload(await call("analyze_text", {"text": TEXT}))
    assert out["overall_score"] == 71.5
    assert [r.url.path for r in api].count("/api/queue/ticket/t1") == 2


async def test_rate_limit_is_retried(api, monkeypatch):
    answers = iter(
        [
            httpx.Response(429, json={"error": "busy", "retry_after": 0}),
            httpx.Response(200, json=REPORT),
        ]
    )
    api.routes[("POST", "/api/analyze")] = lambda r: next(answers)
    out = payload(await call("analyze_text", {"text": TEXT}))
    assert out["overall_verdict"] == "Likely AI"


async def test_analyze_url_adds_a_scheme(api):
    api.routes[("POST", "/api/analyze")] = httpx.Response(
        200, json={**REPORT, "source_type": "url"}
    )
    payload(await call("analyze_url", {"url": "example.com/post"}))
    assert json.loads(api[0].content) == {"url": "https://example.com/post"}


async def test_api_errors_become_tool_errors(api):
    api.routes[("POST", "/api/analyze")] = httpx.Response(
        502, json={"error": "Could not fetch that URL."}
    )
    result = await call("analyze_url", {"url": "https://example.com"})
    assert result.is_error
    assert "Could not fetch that URL." in result.content[0].text


async def test_check_website_builder(api):
    site = {
        "url": "https://x.lovable.app",
        "final_url": "https://x.lovable.app/",
        "site": {"builders": [{"name": "Lovable", "evidence": ["hostname"]}]},
        "text": None,
    }
    api.routes[("POST", "/api/scan/site")] = httpx.Response(200, json=site)
    out = payload(
        await call(
            "check_website_builder",
            {"url": "x.lovable.app", "include_text_score": False},
        )
    )
    assert out["site"]["builders"][0]["name"] == "Lovable"
    assert json.loads(api[0].content) == {"url": "x.lovable.app", "include_text": False}


async def test_no_server_explains_how_to_start_one(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(server, "_transport", httpx.MockTransport(refuse))
    monkeypatch.delenv("SLOPTOTAL_URL", raising=False)
    result = await call("analyze_text", {"text": TEXT})
    assert result.is_error
    assert "ghcr.io/pablocaeg/sloptotal" in result.content[0].text


async def test_proxy_error_page_is_not_dumped(api):
    api.routes[("POST", "/api/scan/site")] = httpx.Response(
        502, text="<!DOCTYPE html><html>cloudflare</html>"
    )
    result = await call("check_website_builder", {"url": "example.com"})
    assert result.is_error
    assert "<html" not in result.content[0].text
    assert "Could not fetch that URL" in result.content[0].text
