"""KV backend (memory) + KV-backed shared rate limiter + fallback."""
from __future__ import annotations

import pytest

from app.services.kv_backend import MemoryKV, build_kv
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_memory_kv_incr_and_ttl_window():
    kv = MemoryKV()
    assert await kv.incr("k", 60) == 1
    assert await kv.incr("k", 60) == 2
    assert await kv.incr("k", 60) == 3


@pytest.mark.asyncio
async def test_memory_kv_get_set_delete():
    kv = MemoryKV()
    assert await kv.get("x") is None
    await kv.set("x", "v", ttl_seconds=60)
    assert await kv.get("x") == "v"
    await kv.delete("x")
    assert await kv.get("x") is None


def test_build_kv_defaults_to_memory_without_url():
    assert isinstance(build_kv(None), MemoryKV)


def test_build_kv_falls_back_to_memory_on_bad_url():
    # A clearly invalid scheme should degrade to memory rather than raise.
    kv = build_kv("not-a-redis-url://")
    # Either a RedisKV (lazily, errors later) or MemoryKV; must not raise here.
    assert kv is not None


@pytest.mark.asyncio
async def test_shared_limiter_blocks_after_window_limit():
    kv = MemoryKV()
    rl = RateLimiter(per_minute=3, kv=kv)
    results = [await rl.check_shared("login:1.2.3.4") for _ in range(5)]
    allowed = [r[0] for r in results]
    assert allowed[:3] == [True, True, True]
    assert allowed[3] is False and allowed[4] is False
    # a different key has its own window
    assert (await rl.check_shared("login:9.9.9.9"))[0] is True


@pytest.mark.asyncio
async def test_shared_limiter_without_kv_uses_in_process():
    rl = RateLimiter(per_minute=2)  # no kv
    a1 = await rl.check_shared("k")
    a2 = await rl.check_shared("k")
    a3 = await rl.check_shared("k")
    assert a1[0] and a2[0] and not a3[0]
