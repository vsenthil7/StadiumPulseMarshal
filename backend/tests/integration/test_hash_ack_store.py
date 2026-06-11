"""Hash-backed burn ack store: per-field isolation, concurrency, parity."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.services.kv_backend import MemoryKV
from app.services.hash_burn_ack_store import HashBurnAckStore


@pytest.mark.asyncio
async def test_per_field_isolation_no_clobber():
    kv = MemoryKV()
    s = HashBurnAckStore(kv)
    # Ack two different alerts; neither should erase the other.
    await s.acknowledge("SLO-A", "page", "alice")
    await s.acknowledge("SLO-B", "ticket", "bob")
    assert (await s.ack_for("SLO-A", "page")).acked_by == "alice"
    assert (await s.ack_for("SLO-B", "ticket")).acked_by == "bob"


@pytest.mark.asyncio
async def test_concurrent_acks_all_survive():
    kv = MemoryKV()
    s = HashBurnAckStore(kv)
    # 20 concurrent acks to distinct fields; all must persist (no doc rewrite race).
    await asyncio.gather(*[
        s.acknowledge(f"SLO-{i}", "page", f"user{i}") for i in range(20)
    ])
    summ = await s.active_summary()
    assert len(summ["acks"]) == 20


@pytest.mark.asyncio
async def test_two_stores_share_hash_over_kv():
    kv = MemoryKV()
    a = HashBurnAckStore(kv)
    b = HashBurnAckStore(kv)
    await a.silence("SLO-X", "ticket", minutes=30, by="bob")
    assert await b.is_silenced("SLO-X", "ticket") is True


@pytest.mark.asyncio
async def test_ack_expiry_and_clear():
    kv = MemoryKV()
    s = HashBurnAckStore(kv, ack_ttl_seconds=0.05)
    await s.acknowledge("SLO-X", "page", "alice")
    assert await s.ack_for("SLO-X", "page") is not None
    time.sleep(0.1)
    assert await s.ack_for("SLO-X", "page") is None  # expired
    await s.silence("SLO-X", "page", 30, "x")
    assert await s.clear_silence("SLO-X", "page") is True
    assert await s.is_silenced("SLO-X", "page") is False


@pytest.mark.asyncio
async def test_summary_prunes_expired():
    kv = MemoryKV()
    s = HashBurnAckStore(kv, ack_ttl_seconds=0.05)
    await s.acknowledge("SLO-OLD", "page", "x")
    await s.silence("SLO-OLD", "page", minutes=0.001, by="x")
    time.sleep(0.1)
    summ = await s.active_summary()
    assert summ["acks"] == [] and summ["silences"] == []
