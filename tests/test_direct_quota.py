"""The daily quota for direct API calls: who is counted and what they get."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import FIRST_PARTY_ORIGINS
from app.direct_quota import DirectQuota, DirectQuotaMiddleware, client_ip


def make_client(limit: int, peer: str = "8.8.8.8") -> TestClient:
    app = FastAPI()

    @app.post("/api/analyze")
    @app.post("/api/web/analyze")
    @app.post("/api/report/{rid}/feedback")
    @app.get("/api/queue/ticket/{tid}")
    async def ok():
        return {"ok": True}

    app.add_middleware(DirectQuotaMiddleware, limit=limit, origins=FIRST_PARTY_ORIGINS)
    return TestClient(app, client=(peer, 50000))


def test_off_by_default_when_limit_is_zero():
    c = make_client(0)
    assert all(c.post("/api/analyze").status_code == 200 for _ in range(20))


def test_direct_calls_stop_at_the_limit_with_a_retry_after():
    c = make_client(3)
    assert [c.post("/api/analyze").status_code for _ in range(4)] == [
        200,
        200,
        200,
        429,
    ]
    r = c.post("/api/web/analyze")
    assert r.status_code == 429
    assert 0 < int(r.headers["retry-after"]) <= 86400
    assert "sloptotal.com" in r.json()["error"]


def test_site_and_extension_are_not_counted():
    c = make_client(1)
    for origin in ("https://sloptotal.com", "chrome-extension://abcdefghijklmnop"):
        for _ in range(5):
            assert c.post("/api/analyze", headers={"Origin": origin}).status_code == 200
    assert (
        c.post("/api/analyze", headers={"Origin": "https://evil.example"}).status_code
        == 200
    )
    assert (
        c.post(
            "/api/analyze", headers={"Origin": "https://sloptotal.com.evil.example"}
        ).status_code
        == 429
    )


def test_feedback_and_polling_are_not_counted():
    c = make_client(1)
    c.post("/api/analyze")
    assert c.post("/api/report/abc/feedback").status_code == 200
    assert c.get("/api/queue/ticket/abc").status_code == 200


def test_quota_resets_each_utc_day():
    q = DirectQuota(1, FIRST_PARTY_ORIGINS)
    day = 20_000 * 86400
    assert q.take("1.2.3.4", day + 10) is None
    assert q.take("1.2.3.4", day + 20) == 86400 - 20
    assert q.take("5.6.7.8", day + 30) is None  # per IP
    assert q.take("1.2.3.4", day + 86400) is None


def test_real_ip_header_is_trusted_only_from_a_private_peer():
    headers = [(b"x-real-ip", b"198.51.100.9")]
    assert (
        client_ip({"client": ("172.17.0.1", 1), "headers": headers}) == "198.51.100.9"
    )
    assert client_ip({"client": ("127.0.0.1", 1), "headers": headers}) == "198.51.100.9"
    assert client_ip({"client": ("8.8.8.8", 1), "headers": headers}) == "8.8.8.8"


def test_each_proxied_ip_has_its_own_allowance():
    c = make_client(1, peer="172.17.0.1")
    a, b = {"X-Real-IP": "198.51.100.1"}, {"X-Real-IP": "198.51.100.2"}
    assert c.post("/api/analyze", headers=a).status_code == 200
    assert c.post("/api/analyze", headers=a).status_code == 429
    assert c.post("/api/analyze", headers=b).status_code == 200
