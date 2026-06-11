"""Token-bucket rate limiter (service).

A small, dependency-free limiter used to protect sensitive endpoints (auth)
independently of the global rate-limit middleware. Keyed by an arbitrary string
(e.g. ``login:<ip>``); refills continuously. Returns whether a request is
allowed and, if not, the seconds until the next token.
"""
from __future__ import annotations

import time


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, capacity: float) -> None:
        self.tokens = capacity
        self.updated = time.monotonic()


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = max(1, per_minute)
        self._buckets: dict[str, _Bucket] = {}

    def check(self, key: str) -> tuple[bool, float]:
        """Consume a token for ``key``. Returns ``(allowed, retry_after_s)``."""
        capacity = float(self.per_minute)
        refill = self.per_minute / 60.0
        now = time.monotonic()
        b = self._buckets.get(key)
        if b is None:
            b = _Bucket(capacity)
            self._buckets[key] = b
        b.tokens = min(capacity, b.tokens + (now - b.updated) * refill)
        b.updated = now
        if b.tokens >= 1.0:
            b.tokens -= 1.0
            return True, 0.0
        return False, (1.0 - b.tokens) / refill

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._buckets.clear()
        else:
            self._buckets.pop(key, None)
