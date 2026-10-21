"""The Go example client posts to /api/analyze and prints the top engines."""

import http.server
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parent.parent / "examples" / "go_client" / "main.go"
GO = shutil.which("go")
TEXT = "This is a sample paragraph that is long enough to be analysed by SlopTotal."
REPORT = {
    "overall_score": 42.0,
    "overall_verdict": "mixed",
    "engine_results": [
        {"engine_name": f"engine_{score}", "score": score, "verdict": "x"}
        for score in (0.10, 0.95, 0.40, 0.85, 0.60, 0.75, 0.20)
    ],
}


def test_go_client_prints_overall_and_top_five_engines():
    if GO is None:
        pytest.skip("go is not installed")

    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append((self.path, json.loads(body)))
            payload = json.dumps(REPORT).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        result = subprocess.run(
            [GO, "run", str(CLIENT), TEXT, "--base", base],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 0, result.stderr

    # The client printed the overall score, verdict, and top five engines.
    assert "Overall score: 42.0/100 (mixed)" in result.stdout
    assert "Top five engines:" in result.stdout

    # The five highest-scoring engines should be listed in descending order.
    # Scores: 0.95, 0.85, 0.75, 0.60, 0.40
    assert "engine_0.95: 95.0%" in result.stdout
    assert "engine_0.85: 85.0%" in result.stdout
    assert "engine_0.4: 40.0%" in result.stdout

    # The request was a POST to /api/analyze with the text in the body.
    assert len(requests) == 1
    path, body = requests[0]
    assert path == "/api/analyze"
    assert body["text"] == TEXT
