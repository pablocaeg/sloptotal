"""A small client for the SlopTotal JSON API: sloptotal.com or your own server."""

import os
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_API = "https://api.sloptotal.com"
DEFAULT_SITE = "https://sloptotal.com"


class SlopTotalError(RuntimeError):
    """The server refused the request or could not be reached."""


@dataclass
class Report:
    score: float
    verdict: str
    word_count: int
    engines: dict[str, float]
    report_id: str
    language: str = "en"
    language_support: str = "supported"
    url: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    def top_engines(self, n: int = 5) -> list[tuple[str, float]]:
        return sorted(self.engines.items(), key=lambda item: item[1], reverse=True)[:n]

    @classmethod
    def from_api(cls, data: dict, url: str = "") -> "Report":
        return cls(
            score=data["overall_score"],
            verdict=data["overall_verdict"],
            word_count=data["word_count"],
            engines={e["engine_name"]: e["score"] for e in data["engine_results"]},
            report_id=data["id"],
            language=data.get("language", "en"),
            language_support=data.get("language_support", "supported"),
            url=url,
            raw=data,
        )


class SlopTotal:
    """`SlopTotal().analyze("some text")`; set SLOPTOTAL_URL to use your own server."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 300.0,
        poll_seconds: float = 2.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (
            base_url or os.environ.get("SLOPTOTAL_URL") or DEFAULT_API
        ).rstrip("/")
        self.poll_seconds = poll_seconds
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": "sloptotal-python"},
            transport=transport,
        )

    def __enter__(self) -> "SlopTotal":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def analyze(self, text: str | None = None, url: str | None = None) -> Report:
        """Run all 23 engines on a text or on the article at a public URL."""
        if bool(text) == bool(url):
            raise ValueError("Pass exactly one of text or url.")
        payload = {"text": text} if text else {"url": url}
        data = self._post_waiting("/api/analyze", payload)
        return Report.from_api(data, self.report_url(data["id"]))

    def report_url(self, report_id: str) -> str:
        """sloptotal.com's report page for the public API; a self-hosted server serves its own."""
        if self.base_url == DEFAULT_API:
            return f"{DEFAULT_SITE}/report/?id={report_id}"
        return f"{self.base_url}/report/{report_id}"

    def check_site(self, url: str) -> dict:
        """Whether a website was built with an AI app builder (Lovable, v0, Bolt, Base44, Replit...)."""
        return self._post_waiting("/api/scan/site", {"url": url})

    def _post_waiting(self, path: str, payload: dict) -> dict:
        response = self._request("POST", path, json=payload)
        while response.status_code == 429:
            time.sleep(float(response.json().get("retry_after", self.poll_seconds)))
            response = self._request("POST", path, json=payload)
        if response.status_code == 202:
            ticket = response.json()["ticket_id"]
            while response.status_code == 202:
                time.sleep(self.poll_seconds)
                response = self._request("GET", f"/api/queue/ticket/{ticket}")
        if response.status_code >= 400:
            try:
                message = response.json().get("error") or response.json().get("detail")
            except ValueError:
                message = response.text[:200]
            raise SlopTotalError(f"{response.status_code}: {message}")
        return response.json()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise SlopTotalError(f"Could not reach {self.base_url}: {error}") from error
