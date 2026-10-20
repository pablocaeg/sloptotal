"""HTTP contract tests. The lifespan (model preload, queue workers) is not
started, so only routes that do not run inference are exercised here; the
full pipeline is covered by the end-to-end run described in .github/CONTRIBUTING.md."""

import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import MIN_TEXT_LENGTH
from app.database import create_report, init_database
from app.documents import extract_document_text
from app.main import app


@pytest.fixture(scope="module")
def client():
    asyncio.run(init_database())
    return TestClient(app)


def test_engines_endpoint_lists_all_engines(client):
    r = client.get("/api/engines")
    assert r.status_code == 200
    body = r.json()
    engines = body["engines"] if isinstance(body, dict) else body
    assert len(engines) == 23


@pytest.mark.parametrize("path", ["/api/analyze", "/api/quick-score"])
def test_rejects_short_text(client, path):
    r = client.post(path, json={"text": "too short"})
    assert r.status_code == 400
    assert f"{MIN_TEXT_LENGTH} characters" in r.json()["error"]


# Issue #84: the length checks used a literal 50, so moving MIN_TEXT_LENGTH
# would have left them behind. These pin the boundary to the constant.
# Only the rejection path is exercised: accepting a text runs inference, which
# this module deliberately does not start.
@pytest.mark.parametrize(
    "path", ["/api/analyze", "/api/quick-score", "/api/paragraph-score"]
)
def test_one_character_short_is_rejected(client, path):
    r = client.post(path, json={"text": "a" * (MIN_TEXT_LENGTH - 1)})
    assert r.status_code == 400
    assert f"{MIN_TEXT_LENGTH} characters" in r.json()["error"]


@pytest.mark.parametrize("path", ["/api/quick-score", "/api/paragraph-score"])
def test_the_length_boundary_tracks_a_changed_min_text_length(
    client, path, monkeypatch
):
    """Raising the constant moves the boundary and the message with it.

    A text that was long enough before is now rejected, which is what a
    hard-coded 50 could not do.
    """
    monkeypatch.setattr("app.routes.api.MIN_TEXT_LENGTH", 500)
    r = client.post(path, json={"text": "a" * 200})
    assert r.status_code == 400
    assert "500 characters" in r.json()["error"]


def test_extract_document_text_follows_min_text_length(monkeypatch):
    """Uploads use the same constant, not their own copy of 50."""
    with pytest.raises(ValueError, match="No readable text found"):
        extract_document_text("short.txt", b"a" * (MIN_TEXT_LENGTH - 1))

    assert extract_document_text("ok.txt", b"a" * MIN_TEXT_LENGTH) == (
        "a" * MIN_TEXT_LENGTH
    )

    monkeypatch.setattr("app.documents.MIN_TEXT_LENGTH", 500)
    with pytest.raises(ValueError, match="No readable text found"):
        extract_document_text("short.txt", b"a" * 200)


@pytest.mark.parametrize("path", ["/api/analyze", "/api/quick-score"])
def test_rejects_empty_request(client, path):
    r = client.post(path, json={})
    assert r.status_code == 400


def test_home_page_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "SlopTotal" in r.text


def test_form_rejects_short_text(client):
    r = client.post("/analyze", data={"text": "short"})
    assert r.status_code == 200
    assert "at least 50 characters" in r.text


def test_unknown_report_returns_html_404(client):
    response = client.get("/report/abc123")

    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "This report does not exist or has expired." in response.text
    assert "Return to homepage" in response.text


def test_invalid_report_id_returns_html_400(client):
    response = client.get("/report/abc-123")

    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]
    assert "This report ID is invalid." in response.text


def test_missing_api_report_still_returns_json(client):
    response = client.get("/api/stream/abc123")

    assert response.status_code == 404
    assert "application/json" in response.headers["content-type"]
    assert response.json()["detail"] == "Report not found"


def test_health(client):
    from app.engine_status import mark_failed, mark_loaded, reset_status

    reset_status()
    mark_loaded("perplexity")
    mark_loaded("classifier_tmr")
    mark_failed("classifier_superannotate", "test failure")

    r = client.get("/health")

    assert r.status_code == 200
    assert r.json()["engines"]["total"] == 23
    assert r.json()["engines"]["loaded"] == 2
    assert r.json()["engines"]["failed"] == ["classifier_superannotate"]


def test_site_scan_requires_url(client):
    assert client.post("/api/scan/site", json={}).status_code == 400


def test_url_scans_refuse_private_addresses(client):
    r = client.post("/api/scan/site", json={"url": "http://127.0.0.1:8000/health"})
    assert r.status_code == 400
    assert "private" in r.json()["error"]


def test_extract_endpoint(client):
    from tests.samples import AI_TEXT

    r = client.post(
        "/api/extract", files={"file": ("essay.txt", AI_TEXT.encode(), "text/plain")}
    )
    assert r.status_code == 200
    assert r.json()["word_count"] == len(AI_TEXT.split())
    r = client.post(
        "/api/extract",
        files={"file": ("x.exe", b"MZ" * 50, "application/octet-stream")},
    )
    assert r.status_code == 400


@pytest.mark.parametrize("path", ["/api/analyze", "/api/web/analyze"])
def test_unreachable_url_is_a_502_not_a_crash(client, monkeypatch, path):
    async def times_out(url):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(
        f"app.routes.{'web' if 'web' in path else 'api'}.extract_text_from_url",
        times_out,
    )
    r = client.post(path, json={"url": "https://unreachable.example"})
    assert r.status_code == 502
    assert r.json()["error"] == "Could not fetch that URL."


def test_a_report_says_which_language_it_scored(client):
    from datetime import datetime

    from app.schemas import AnalysisReport

    report = AnalysisReport(
        id="abc",
        source_type="text",
        source="x",
        text_excerpt="El ayuntamiento aprobó el plan después de varios meses de debate, y los vecinos dijeron que no se les había consultado.",
        word_count=20,
        engine_results=[],
        overall_score=10.0,
        overall_verdict="Clean",
        engines_flagged=0,
        engines_total=23,
        created_at=datetime(2026, 10, 1),
    )
    dumped = report.model_dump()
    assert dumped["language"] == "es"
    assert dumped["language_support"] in {"supported", "experimental", "unsupported"}


def test_api_paths_have_tags(client):
    openapi = client.app.openapi()
    for path, methods in openapi["paths"].items():
        if path.startswith("/api"):
            for method, method_data in methods.items():
                if method.lower() in (
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "options",
                    "head",
                ):
                    assert method_data.get("tags"), f"{path} {method} missing tags"


def test_upload_status_is_accessible_live_region(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'id="upload-status"' in html
    assert 'aria-live="polite"' in html
    assert 'role="status"' in html


def test_report_shows_detected_language(client):
    report_id = uuid4().hex[:12]

    asyncio.run(
        create_report(
            report_id=report_id,
            text_hash="a" * 64,
            source_type="text",
            source="",
            text_excerpt=(
                "The quick brown fox jumps over the lazy dog. "
                "This is a simple English sentence with the words "
                "the, and, of, to, in, is, that, it, for, and was. "
            ),
            word_count=25,
            engines_total=23,
        )
    )

    response = client.get(f"/report/{report_id}")

    assert response.status_code == 200
    assert "Language:" in response.text
    assert "<b>en</b>" in response.text


def test_report_hides_unknown_language(client):
    report_id = uuid4().hex[:12]

    asyncio.run(
        create_report(
            report_id=report_id,
            text_hash="b" * 64,
            source_type="text",
            source="",
            text_excerpt="12345 !!!",
            word_count=0,
            engines_total=23,
        )
    )

    response = client.get(f"/report/{report_id}")

    assert response.status_code == 200
    assert "Language:" not in response.text


def test_scan_stats_shows_no_texts_or_urls(client):
    """The endpoint is public: aggregates only, never the scanned texts or URLs."""
    from app.database import log_scan_sync

    log_scan_sync(
        scan_type="url",
        text_excerpt="a private page someone read",
        text_hash="c" * 64,
        chars=27,
        score=50.0,
        indicator="yellow",
        confidence="low",
        bert=0.5,
        e5=0.5,
        tmr=0.5,
        fakespot=0.5,
        source_url="https://private.example/page",
    )
    r = client.get("/api/scan/stats")
    assert r.status_code == 200
    assert "recent" not in r.json()
    assert "private" not in r.text


def test_health_does_not_show_the_database_path(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "database_path" not in r.json()["database"]
