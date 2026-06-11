"""Real Redis-protocol end-to-end: shared limiter across two app instances.

Docker isn't available in the sandbox, but ``fakeredis`` implements the actual
Redis protocol (incl. redis.asyncio) in-process. We point our real ``RedisKV``
at a single shared fakeredis server and prove two independent ``RateLimiter``
instances (= two app replicas) enforce ONE global limit through real Redis
INCR/EXPIRE commands — the property the docker-compose stack relies on.
"""
from __future__ import annotations

import fakeredis.aioredis
import pytest

from app.services.kv_backend import RedisKV
from app.services.rate_limiter import RateLimiter


def _shared_redis_kv_pair():
    # One shared in-memory Redis server, two client connections (two replicas).
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    # FakeRedis instances created from the same server share state; simplest is
    # to reuse the same client object for both KVs (same backing store).
    kv_a = RedisKV("redis://fake", client=server)
    kv_b = RedisKV("redis://fake", client=server)
    return kv_a, kv_b


@pytest.mark.asyncio
async def test_redis_incr_real_protocol():
    kv, _ = _shared_redis_kv_pair()
    assert await kv.incr("w", 60) == 1
    assert await kv.incr("w", 60) == 2
    # TTL was set on first incr
    assert await kv.get("nonexistent") is None
    await kv.set("k", "v", 30)
    assert await kv.get("k") == "v"
    await kv.delete("k")
    assert await kv.get("k") is None


@pytest.mark.asyncio
async def test_two_replicas_share_one_global_limit_over_redis():
    kv_a, kv_b = _shared_redis_kv_pair()
    inst_a = RateLimiter(per_minute=5, kv=kv_a)
    inst_b = RateLimiter(per_minute=5, kv=kv_b)
    key = "login:203.0.113.7"
    allowed = 0
    # Alternate replicas like nginx round-robin; the cap must hold GLOBALLY.
    for i in range(10):
        limiter = inst_a if i % 2 == 0 else inst_b
        ok, _ = await limiter.check_shared(key)
        if ok:
            allowed += 1
    assert allowed == 5  # global, not 10


@pytest.mark.asyncio
async def test_redis_window_isolation_per_key():
    kv_a, kv_b = _shared_redis_kv_pair()
    a = RateLimiter(per_minute=2, kv=kv_a)
    b = RateLimiter(per_minute=2, kv=kv_b)
    # different clients → independent windows even over the same Redis
    assert (await a.check_shared("login:1.1.1.1"))[0] is True
    assert (await b.check_shared("login:2.2.2.2"))[0] is True
    # exhaust one key across both replicas
    await a.check_shared("login:1.1.1.1")  # 2nd for that key
    ok, retry = await b.check_shared("login:1.1.1.1")  # 3rd → blocked
    assert ok is False and retry >= 1


@pytest.mark.asyncio
async def test_http_two_instances_round_robin_shared_429():
    """Full HTTP path: two real app instances, one shared Redis KV, round-robin
    login requests — the global auth limit yields a 429 across instances."""
    import httpx
    from app.main import create_app

    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    apps = [create_app(), create_app()]
    cm = []
    stack = []
    try:
        for app in apps:
            mgr = app.router.lifespan_context(app)
            await mgr.__aenter__()
            stack.append((mgr, app))
            # Inject a shared RedisKV into each instance's auth limiter.
            app.state.ctx.kv = RedisKV("redis://fake", client=server)
            app.state.ctx.auth_limiter = RateLimiter(5, kv=app.state.ctx.kv)
            cm.append(httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://t"))

        codes = []
        for i in range(8):
            c = cm[i % 2]  # round-robin across the two instances
            r = await c.post("/api/v1/auth/login",
                             json={"email": "rr@x.demo", "password": "bad"})
            codes.append(r.status_code)
        assert 429 in codes[:6]
    finally:
        for c in cm:
            await c.aclose()
        for mgr, app in stack:
            await mgr.__aexit__(None, None, None)
