"""Daily quota for API calls made outside the site and the browser extension.

The hosted instance is meant to be used through sloptotal.com and the extension.
Scripts that call the API directly share the same queue as those users, so each
client IP gets a small daily allowance there, enough to try the API, and anyone
who needs more can run their own instance.

Off by default (`SLOPTOTAL_DIRECT_DAILY_LIMIT=0`), so self-hosted instances are
not affected. A request counts as first party when its Origin header matches
FIRST_PARTY_ORIGINS. That header is easy to forge, so this is a quota for honest
scripts, not a security boundary.
"""

import ipaddress
import re
import threading
import time

from starlette.responses import JSONResponse

from app.config import DIRECT_DAILY_LIMIT, FIRST_PARTY_ORIGINS

# Requests that start work on the server. Polling a ticket or a stream, reading a
# report and sending feedback are not counted.
_COUNTED = re.compile(r"^/(analyze$|api/(?!report/)(?!queue/))")

_MESSAGE = (
    "Daily limit for direct API use reached. Use https://sloptotal.com, or run "
    "your own instance for unlimited use: https://github.com/pablocaeg/sloptotal"
)


def client_ip(scope) -> str:
    """The caller's IP. X-Real-IP is trusted only when the connection comes from
    a private or loopback address, which is where a reverse proxy sits."""
    peer = (scope.get("client") or ("", 0))[0]
    try:
        trusted = ipaddress.ip_address(peer).is_private
    except ValueError:
        trusted = False
    if trusted:
        for name, value in scope.get("headers", []):
            if name == b"x-real-ip":
                return value.decode("latin-1").strip() or peer
    return peer


class DirectQuota:
    """Counts direct calls per IP per UTC day."""

    def __init__(self, limit: int, origins: str):
        self.limit = limit
        self.origins = re.compile(origins)
        self._day = 0
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def counts(self, method: str, path: str, origin: str) -> bool:
        if self.limit <= 0 or method != "POST" or not _COUNTED.match(path):
            return False
        return not (origin and self.origins.match(origin))

    def take(self, ip: str, now: float | None = None) -> int | None:
        """Use one call. Returns None if allowed, else seconds until the reset."""
        now = time.time() if now is None else now
        day = int(now // 86400)
        with self._lock:
            if day != self._day:
                self._day, self._counts = day, {}
            used = self._counts.get(ip, 0)
            if used >= self.limit:
                return (day + 1) * 86400 - int(now)
            self._counts[ip] = used + 1
            return None


class DirectQuotaMiddleware:
    def __init__(
        self, app, limit: int = DIRECT_DAILY_LIMIT, origins: str = FIRST_PARTY_ORIGINS
    ):
        self.app = app
        self.quota = DirectQuota(limit, origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            origin = headers.get(b"origin", b"").decode("latin-1")
            if self.quota.counts(scope["method"], scope["path"], origin):
                wait = self.quota.take(client_ip(scope))
                if wait is not None:
                    response = JSONResponse(
                        {"error": _MESSAGE, "retry_after": wait},
                        status_code=429,
                        headers={"Retry-After": str(wait)},
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
