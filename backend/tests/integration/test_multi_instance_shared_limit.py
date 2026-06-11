"""In-sandbox proof of cross-instance shared rate limiting.

Docker/Redis aren't available in the sandbox, so we prove the *property* the
compose stack relies on: two independent app instances that share one KV backend
enforce a single global limit (exactly what Redis provides across replicas).
With two separate in-process limiters (no shared KV) the limit would be
per-instance and the global cap would be double.
"""
from __future__ import annotations

import pytest

from app.services.kv_backend import MemoryKV
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_two_instances_sharing_kv_enforce_one_global_limit():
    # One shared KV stands in for Redis; two limiters = two app replicas.
    shared = MemoryKV()
    inst_a = RateLimiter(per_minute=5, kv=shared)
    inst_b = RateLimiter(per_minute=5, kv=shared)

    key = "login:1.2.3.4"
    allowed = 0
    # Alternate replicas like an nginx round-robin.
    for i in range(8):
        limiter = inst_a if i % 2 == 0 else inst_b
        ok, _ = await limiter.check_shared(key)
        if ok:
            allowed += 1
    # Global cap of 5 holds ACROSS both instances (not 10).
    assert allowed == 5


@pytest.mark.asyncio
async def test_independent_kv_would_not_share_limit():
    # Control: separate KVs (no Redis) → each instance has its own window, so
    # the effective cap doubles. This is what we're avoiding in production.
    a = RateLimiter(per_minute=5, kv=MemoryKV())
    b = RateLimiter(per_minute=5, kv=MemoryKV())
    key = "login:1.2.3.4"
    allowed = 0
    for i in range(12):
        limiter = a if i % 2 == 0 else b
        ok, _ = await limiter.check_shared(key)
        if ok:
            allowed += 1
    assert allowed == 10  # 5 per independent instance


@pytest.mark.asyncio
async def test_shared_limit_returns_retry_after():
    shared = MemoryKV()
    rl = RateLimiter(per_minute=2, kv=shared)
    await rl.check_shared("k")
    await rl.check_shared("k")
    ok, retry = await rl.check_shared("k")
    assert ok is False and retry >= 1
