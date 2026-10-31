"""Protections for a public deployment: access code, rate limits, and security headers.

A deployed demo spends real model credits, so three layers keep it bounded:
- an optional access code (`ACCESS_CODE`), sent by the UI as `X-Access-Code`;
- per-client rate limits on the endpoints that call the model, and on code attempts;
- a daily token budget (app.llm.budget), after which answers fall back to offline mode.
The limiter keeps its counters in memory, which is accurate when the service runs as a
single instance (the Cloud Run deployment sets max instances to 1).
"""

import hmac
import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import Settings

logger = logging.getLogger(__name__)

ACCESS_HEADER = "x-access-code"
# Requests that call the model (and so cost money) are rate limited.
MODEL_ENDPOINTS = ("/api/v1/chat", "/api/v1/agent/stream", "/api/v1/agent/run",
                   "/api/v1/agent/runs/")  # fmt: skip
# Open without a code: liveness, the code check itself, and the UI's static files.
OPEN_PREFIXES = ("/health", "/api/v1/access")


def client_ip(request: Request, forwarded_hops: int) -> str:
    """The caller's address. Behind N trusted proxies, the Nth address from the right of
    X-Forwarded-For is the one the outermost proxy saw; anything left of it is supplied by
    the client and can be forged."""
    if forwarded_hops > 0:
        hops = [
            h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()
        ]
        if len(hops) >= forwarded_hops:
            return hops[-forwarded_hops]
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, now: float | None = None) -> float | None:
        """Record a request. Returns None if allowed, else seconds until a slot frees up."""
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return hits[0] + self.window - now
        hits.append(now)
        if len(self._hits) > 10_000:  # forget idle clients
            for k in [k for k, v in self._hits.items() if not v]:
                del self._hits[k]
        return None


def access_code_valid(settings: Settings, supplied: str | None) -> bool:
    if settings.access_code is None:
        return True
    expected = settings.access_code.get_secret_value().encode()
    return hmac.compare_digest(expected, (supplied or "").encode())


def _limited(retry_after: float, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=429,
                        headers={"Retry-After": str(max(1, round(retry_after)))})  # fmt: skip


class ProtectionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings
        self.model_limiter = (
            SlidingWindowLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
            if settings.rate_limit_requests
            else None
        )
        self.code_limiter = SlidingWindowLimiter(10, 600)  # code guesses per client

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        ip = client_ip(request, self.settings.forwarded_hops)
        if path.startswith("/api/") and not path.startswith(OPEN_PREFIXES):
            if not access_code_valid(self.settings, request.headers.get(ACCESS_HEADER)):
                if (
                    request.headers.get(ACCESS_HEADER)
                    and (wait := self.code_limiter.hit(ip)) is not None
                ):
                    return _limited(wait, "Too many access-code attempts. Try again later.")
                return JSONResponse({"detail": "An access code is required."}, status_code=401)
            if (
                self.model_limiter
                and request.method == "POST"
                and path.startswith(MODEL_ENDPOINTS)
                and (wait := self.model_limiter.hit(ip)) is not None
            ):
                logger.warning("Rate limit reached for %s on %s", ip, path)
                return _limited(wait, "Too many questions in a short time. Please wait a bit.")
        if (
            path == "/api/v1/access"
            and request.method == "POST"
            and (wait := self.code_limiter.hit(ip)) is not None
        ):
            return _limited(wait, "Too many access-code attempts. Try again later.")
        response = await call_next(request)
        _security_headers(response, self.settings)
        return response


def _security_headers(response: Response, settings: Settings) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if settings.app_env == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")


def install_protection(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(ProtectionMiddleware, settings=settings)
