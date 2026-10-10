import json

import httpx
import pytest

from sloptotal import cli
from sloptotal.client import SlopTotal, SlopTotalError

REPORT = {
    "id": "abc123",
    "overall_score": 72.4,
    "overall_verdict": "Likely AI-generated",
    "word_count": 240,
    "language": "en",
    "language_support": "supported",
    "engine_results": [
        {"engine_name": "Desklib DeBERTa", "score": 0.99},
        {"engine_name": "Perplexity", "score": 0.4},
        {"engine_name": "ReMoDetect", "score": 0.95},
    ],
}


def server(*responses):
    """A fake API that answers each request with the next response in turn."""
    queue = list(responses)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler), seen


def test_a_finished_report_is_returned_with_its_link():
    transport, _ = server((200, REPORT))
    report = SlopTotal("http://x", transport=transport).analyze(text="some text")

    assert report.score == 72.4
    assert report.top_engines(2) == [("Desklib DeBERTa", 0.99), ("ReMoDetect", 0.95)]
    assert report.url == "http://x/report/abc123"


def test_the_public_api_links_to_the_report_on_sloptotal_com(monkeypatch):
    monkeypatch.delenv("SLOPTOTAL_URL", raising=False)
    assert SlopTotal().report_url("abc") == "https://sloptotal.com/report/?id=abc"


def test_a_queued_request_is_polled_with_the_first_ticket_id():
    transport, seen = server(
        (202, {"status": "queued", "ticket_id": "t1"}),
        (202, {"status": "queued", "position": 1}),
        (200, REPORT),
    )
    report = SlopTotal("http://x", poll_seconds=0, transport=transport).analyze(
        text="some text"
    )

    assert report.report_id == "abc123"
    assert seen == [
        ("POST", "/api/analyze"),
        ("GET", "/api/queue/ticket/t1"),
        ("GET", "/api/queue/ticket/t1"),
    ]


def test_a_busy_server_is_retried_after_it_says_when():
    transport, seen = server((429, {"error": "busy", "retry_after": 0}), (200, REPORT))
    SlopTotal("http://x", transport=transport).analyze(text="some text")
    assert [path for _, path in seen] == ["/api/analyze", "/api/analyze"]


def test_a_refusal_raises_with_the_server_message():
    transport, _ = server((400, {"error": "Text must be at least 50 characters."}))
    with pytest.raises(SlopTotalError, match="at least 50 characters"):
        SlopTotal("http://x", transport=transport).analyze(text="short")


def test_exactly_one_of_text_or_url():
    with pytest.raises(ValueError):
        SlopTotal("http://x").analyze()


@pytest.fixture
def fake_api(monkeypatch):
    real_init = SlopTotal.__init__

    def use(*responses):
        transport, _ = server(*responses)

        def init(self, base_url=None, **kwargs):
            real_init(self, "http://x", transport=transport, poll_seconds=0)

        monkeypatch.setattr(SlopTotal, "__init__", init)

    return use


def test_check_exits_1_only_above_the_threshold(fake_api, tmp_path, capsys):
    essay = tmp_path / "essay.md"
    essay.write_text("some text")

    fake_api((200, REPORT))
    assert cli.main(["check", str(essay), "--fail-above", "80"]) == 0
    fake_api((200, REPORT))
    assert cli.main(["check", str(essay), "--fail-above", "55"]) == 1
    assert "72.4" in capsys.readouterr().out


def test_check_prints_json(fake_api, tmp_path, capsys):
    essay = tmp_path / "essay.md"
    essay.write_text("some text")
    fake_api((200, REPORT))

    assert cli.main(["check", str(essay), "--json"]) == 0
    [row] = json.loads(capsys.readouterr().out)
    assert row["score"] == 72.4 and row["report_url"] == "http://x/report/abc123"


def test_short_text_and_language_caveats_are_printed(fake_api, tmp_path, capsys):
    essay = tmp_path / "corto.txt"
    essay.write_text("texto")
    fake_api(
        (
            200,
            {
                **REPORT,
                "word_count": 30,
                "language": "tr",
                "language_support": "unsupported",
            },
        )
    )

    cli.main(["check", str(essay)])
    out = capsys.readouterr().out
    assert "under 80 words" in out and "(tr) is unsupported" in out


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.startswith("sloptotal 0.")


def test_check_with_nothing_to_read_explains_instead_of_waiting(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert cli.main(["check"]) == 2
    assert "Nothing to check" in capsys.readouterr().err
