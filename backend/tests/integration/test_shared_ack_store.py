"""Shared (KV-backed) burn ack/silence store: cross-instance + expiry."""
from __future__ import annotations

import time

import pytest

from app.services.kv_backend import MemoryKV
from app.services.shared_burn_ack_store import SharedBurnAckStore


@pytest.mark.asyncio
async def test_two_instances_share_ack_over_kv():
    kv = MemoryKV()
    a = SharedBurnAckStore(kv)
    b = SharedBurnAckStore(kv)
    await a.acknowledge("SLO-X", "page", "alice", "investigating")
    # second instance sees the ack
    rec = await b.ack_for("SLO-X", "page")
    assert rec is not None and rec.acked_by == "alice"


@pytest.mark.asyncio
async def test_silence_shared_and_suppresses_on_other_instance():
    kv = MemoryKV()
    a = SharedBurnAckStore(kv)
    b = SharedBurnAckStore(kv)
    await a.silence("SLO-X", "ticket", minutes=30, by="bob")
    assert await b.is_silenced("SLO-X", "ticket") is True


@pytest.mark.asyncio
async def test_ack_expiry_drops_on_read():
    kv = MemoryKV()
    s = SharedBurnAckStore(kv, ack_ttl_seconds=0.05)
    await s.acknowledge("SLO-X", "page", "alice")
    assert await s.ack_for("SLO-X", "page") is not None
    time.sleep(0.1)
    assert await s.ack_for("SLO-X", "page") is None


@pytest.mark.asyncio
async def test_silence_expiry():
    kv = MemoryKV()
    s = SharedBurnAckStore(kv)
    await s.silence("SLO-X", "page", minutes=0.001, by="x")
    assert await s.is_silenced("SLO-X", "page") is True
    time.sleep(0.1)
    assert await s.is_silenced("SLO-X", "page") is False


@pytest.mark.asyncio
async def test_clear_ack_and_silence():
    kv = MemoryKV()
    s = SharedBurnAckStore(kv)
    await s.acknowledge("SLO-X", "page", "alice")
    assert await s.clear_ack("SLO-X", "page") is True
    assert await s.ack_for("SLO-X", "page") is None
    await s.silence("SLO-X", "page", minutes=30, by="x")
    assert await s.clear_silence("SLO-X", "page") is True
    assert await s.is_silenced("SLO-X", "page") is False


@pytest.mark.asyncio
async def test_active_summary():
    kv = MemoryKV()
    s = SharedBurnAckStore(kv)
    await s.acknowledge("SLO-A", "page", "alice")
    await s.silence("SLO-B", "ticket", minutes=30, by="bob")
    summ = await s.active_summary()
    assert len(summ["acks"]) == 1 and summ["acks"][0]["slo_id"] == "SLO-A"
    assert len(summ["silences"]) == 1 and summ["silences"][0]["slo_id"] == "SLO-B"
