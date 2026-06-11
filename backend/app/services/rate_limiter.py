"""Token-bucket rate limiter (service).

A small, dependency-free limiter used to protect sensitive endpoints (auth)
independently of the global rate-limit middleware. Keyed by an arbitrary string
(e.g. ``login:<ip>``).

Two modes:
- in-process token bucket (default; ``check``) — smooth refill, single instance;
- shared fixed-window over a ``KVBackend`` (``check_shared``) — atomic across
  instances when a Redis KV is configured, so limits are global in a cluster.
"""
from __future__ import annotations

import time

from app.services.kv_backend import KVBackend


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, capacity: float) -> None:
        self.tokens = capacity
        self.updated = time.monotonic()


class RateLimiter:
    def __init__(self, per_minute: int, kv: KVBackend | None = None) -> None:
        self.per_minute = max(1, per_minute)
        self._buckets: dict[str, _Bucket] = {}
        self._kv = kv

    def check(self, key: str) -> tuple[bool, float]:
        """In-process token bucket. Returns ``(allowed, retry_after_s)``."""
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

    async def check_shared(self, key: str) -> tuple[bool, float]:
        """Shared fixed-window limit over the KV backend.

        Atomic across instances: increments a per-minute-window counter; once it
        exceeds ``per_minute`` the request is denied until the window rolls. When
        no KV is configured this delegates to the in-process bucket.
        """
        if self._kv is None:
            return self.check(key)
        window = int(time.time() // 60)
        wkey = f"rl:{key}:{window}"
        count = await self._kv.incr(wkey, ttl_seconds=60)
        if count <= self.per_minute:
            return True, 0.0
        retry = 60 - int(time.time() % 60)
        return False, float(max(1, retry))

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._buckets.clear()
        else:
            self._buckets.pop(key, None)
