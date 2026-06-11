"""Token-bucket rate limiting middleware.

Per-client (API key or remote IP) token bucket. Refills continuously at
``rate_limit_per_minute``/60 tokens per second up to a burst capacity. Over the
limit returns a 429 envelope with ``Retry-After``. The /metrics, /health and
/ready endpoints are exempt so monitoring is never throttled.
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import error_envelope
from app.middleware.correlation import get_request_id

_EXEMPT_PATHS = {"/api/v1/metrics", "/api/v1/health", "/api/v1/ready"}


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, capacity: float) -> None:
        self.tokens = capacity
        self.updated = time.monotonic()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._buckets: dict[str, _Bucket] = {}

    def _client_key(self, request: Request) -> str:
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"key:{api_key}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    def _allow(self, key: str, rate_per_min: int) -> tuple[bool, float]:
        capacity = float(rate_per_min)
        refill_per_sec = rate_per_min / 60.0
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(capacity)
            self._buckets[key] = bucket
        elapsed = now - bucket.updated
        bucket.tokens = min(capacity, bucket.tokens + elapsed * refill_per_sec)
        bucket.updated = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True, 0.0
        # seconds until one token is available
        retry = (1.0 - bucket.tokens) / refill_per_sec
        return False, retry

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)
        settings = request.app.state.ctx.settings
        allowed, retry = self._allow(
            self._client_key(request), settings.rate_limit_per_minute
        )
        if not allowed:
            retry_after = max(1, int(retry + 0.999))
            return JSONResponse(
                status_code=429,
                content=error_envelope(
                    "rate_limited", "Rate limit exceeded", get_request_id(),
                    {"retry_after": retry_after},
                ),
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
