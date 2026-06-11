"""Shared key-value backend for cross-instance state.

A tiny async KV abstraction so rate-limiting (and any future cross-instance
counters/flags) work when the app runs as more than one process/replica. Two
implementations:

- ``MemoryKV`` — process-local (single-instance / demo / tests);
- ``RedisKV`` — shared across instances (production), used when ``REDIS_URL`` is
  set. redis-py is imported lazily so the dependency is optional.

The interface is intentionally minimal: an atomic ``incr`` with a first-write
expiry (enough for fixed-window rate limiting) plus get/set/delete.
"""
from __future__ import annotations

import time
from typing import Protocol


class KVBackend(Protocol):
    async def incr(self, key: str, ttl_seconds: int) -> int:
        """Atomically increment ``key`` and return the new value. Sets the TTL
        on first creation so the counter self-expires (fixed window)."""
        ...

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def close(self) -> None: ...
    # Hash ops (per-field) — let callers update one field without rewriting the
    # whole value, avoiding last-write-wins races across fields.
    async def hset(self, key: str, field: str, value: str) -> None: ...
    async def hget(self, key: str, field: str) -> str | None: ...
    async def hdel(self, key: str, field: str) -> bool: ...
    async def hgetall(self, key: str) -> dict[str, str]: ...


class MemoryKV:
    """Process-local KV with TTL. Suitable for single-instance deployments."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float | None]] = {}
        self._counters: dict[str, tuple[int, float]] = {}
        self._hashes: dict[str, dict[str, str]] = {}

    def _expired(self, exp: float | None) -> bool:
        return exp is not None and exp < time.monotonic()

    async def incr(self, key: str, ttl_seconds: int) -> int:
        now = time.monotonic()
        cur = self._counters.get(key)
        if cur is None or cur[1] < now:
            self._counters[key] = (1, now + ttl_seconds)
            return 1
        n = cur[0] + 1
        self._counters[key] = (n, cur[1])
        return n

    async def get(self, key: str) -> str | None:
        v = self._values.get(key)
        if v is None or self._expired(v[1]):
            self._values.pop(key, None)
            return None
        return v[0]

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        exp = time.monotonic() + ttl_seconds if ttl_seconds else None
        self._values[key] = (value, exp)

    async def delete(self, key: str) -> None:
        self._values.pop(key, None)
        self._counters.pop(key, None)
        self._hashes.pop(key, None)

    async def hset(self, key: str, field: str, value: str) -> None:
        self._hashes.setdefault(key, {})[field] = value

    async def hget(self, key: str, field: str) -> str | None:
        return self._hashes.get(key, {}).get(field)

    async def hdel(self, key: str, field: str) -> bool:
        h = self._hashes.get(key)
        if h is not None and field in h:
            del h[field]
            return True
        return False

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def close(self) -> None:
        return None


class RedisKV:
    """Redis-backed KV shared across instances. redis-py imported lazily."""

    def __init__(self, url: str, client=None) -> None:
        if client is not None:
            self._r = client
        else:
            import redis.asyncio as aioredis  # lazy import; optional dependency

            self._r = aioredis.from_url(url, encoding="utf-8", decode_responses=True)

    async def incr(self, key: str, ttl_seconds: int) -> int:
        # Pipeline INCR + (conditional) EXPIRE so the window self-clears.
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = await pipe.execute()
        if ttl is None or ttl < 0:
            await self._r.expire(key, ttl_seconds)
        return int(count)

    async def get(self, key: str) -> str | None:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        await self._r.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def hset(self, key: str, field: str, value: str) -> None:
        await self._r.hset(key, field, value)

    async def hget(self, key: str, field: str) -> str | None:
        return await self._r.hget(key, field)

    async def hdel(self, key: str, field: str) -> bool:
        return bool(await self._r.hdel(key, field))

    async def hgetall(self, key: str) -> dict[str, str]:
        return await self._r.hgetall(key) or {}

    async def close(self) -> None:
        try:
            await self._r.aclose()
        except Exception:  # noqa: BLE001
            pass


def build_kv(redis_url: str | None) -> KVBackend:
    """Redis KV when a URL is configured (and importable), else memory.

    Falls back to memory if redis-py is missing so a misconfiguration degrades
    to single-instance behaviour rather than failing to boot.
    """
    if redis_url:
        try:
            return RedisKV(redis_url)
        except Exception:  # noqa: BLE001 - missing dep / bad url → degrade
            pass
    return MemoryKV()
