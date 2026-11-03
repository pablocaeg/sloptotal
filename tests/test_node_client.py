"""The Node example client posts to /api/analyze and prints the top engines."""

import http.server
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parent.parent / "examples" / "node_client.mjs"
NODE = shutil.which("node")
TEXT = "This is a sample paragraph that is long enough to be analysed by SlopTotal."
REPORT = {
    "overall_score": 42.0,
    "overall_verdict": "mixed",
    "engine_results": [
        {"engine_name": f"engine_{score}", "score": score, "verdict": "x"}
        for score in (0.10, 0.95, 0.40, 0.85, 0.60, 0.75, 0.20)
    ],
}


def test_node_client_prints_overall_and_top_five_engines():
    if NODE is None:
        pytest.skip("node is not installed")

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
            [NODE, str(CLIENT), TEXT, "--base", base],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 0, result.stderr
    assert requests == [("/api/analyze", {"text": TEXT})]
    assert result.stdout.splitlines() == [
        "Overall score: 42.0/100 (mixed)",
        "Top five engines:",
        "  engine_0.95: 95.0%",
        "  engine_0.85: 85.0%",
        "  engine_0.75: 75.0%",
        "  engine_0.6: 60.0%",
        "  engine_0.4: 40.0%",
    ]
