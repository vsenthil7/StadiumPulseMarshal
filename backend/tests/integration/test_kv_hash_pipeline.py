"""hgetall_many parity across Memory + real Redis protocol (fakeredis)."""
from __future__ import annotations

import fakeredis.aioredis
import pytest

from app.services.kv_backend import MemoryKV, RedisKV


@pytest.mark.asyncio
async def test_memory_hgetall_many():
    kv = MemoryKV()
    await kv.hset("h1", "a", "1")
    await kv.hset("h1", "b", "2")
    await kv.hset("h2", "x", "9")
    out = await kv.hgetall_many(["h1", "h2", "missing"])
    assert out["h1"] == {"a": "1", "b": "2"}
    assert out["h2"] == {"x": "9"}
    assert out["missing"] == {}


@pytest.mark.asyncio
async def test_redis_hgetall_many_pipelined():
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    kv = RedisKV("redis://fake", client=server)
    await kv.hset("h1", "a", "1")
    await kv.hset("h2", "x", "9")
    out = await kv.hgetall_many(["h1", "h2", "nope"])
    assert out["h1"]["a"] == "1" and out["h2"]["x"] == "9" and out["nope"] == {}


@pytest.mark.asyncio
async def test_summary_uses_pipelined_read():
    # active_summary should reflect both hashes via the multi-read.
    from app.services.hash_burn_ack_store import HashBurnAckStore
    kv = MemoryKV()
    s = HashBurnAckStore(kv)
    await s.acknowledge("SLO-A", "page", "alice")
    await s.silence("SLO-B", "ticket", 30, "bob")
    summ = await s.active_summary()
    assert len(summ["acks"]) == 1 and len(summ["silences"]) == 1
