"""Targeted coverage closeout for service/model branches (V39+)."""
from __future__ import annotations

import json
import time

import httpx
import pytest

from app.services.kv_backend import MemoryKV
from app.services.digest_mute_store import DigestMuteStore, _KEY as MUTE_KEY
from app.services.burn_counters import BurnCounters, _TOTAL


@pytest.mark.asyncio
async def test_mute_unmute_and_is_muted():
    store = DigestMuteStore(MemoryKV())
    until = await store.mute("V-1", minutes=10, by="sre-sam")
    assert until > time.time()
    assert await store.is_muted("V-1") is True
    assert await store.unmute("V-1") is True
    assert await store.is_muted("V-1") is False


@pytest.mark.asyncio
async def test_is_muted_unknown_venue_false():
    store = DigestMuteStore(MemoryKV())
    assert await store.is_muted("nope") is False


@pytest.mark.asyncio
async def test_is_muted_malformed_json_false():
    kv = MemoryKV()
    await kv.hset(MUTE_KEY, "V-bad", "{not-json")
    store = DigestMuteStore(kv)
    assert await store.is_muted("V-bad") is False


@pytest.mark.asyncio
async def test_is_muted_expired_prunes_and_false():
    kv = MemoryKV()
    await kv.hset(MUTE_KEY, "V-exp", json.dumps({"until": time.time() - 1, "by": "x"}))
    store = DigestMuteStore(kv)
    assert await store.is_muted("V-exp") is False
    assert await kv.hget(MUTE_KEY, "V-exp") is None


@pytest.mark.asyncio
async def test_active_filters_expired_and_malformed():
    kv = MemoryKV()
    await kv.hset(MUTE_KEY, "V-live", json.dumps({"until": time.time() + 600, "by": "sam"}))
    await kv.hset(MUTE_KEY, "V-exp", json.dumps({"until": time.time() - 5, "by": "old"}))
    await kv.hset(MUTE_KEY, "V-bad", "garbage")
    store = DigestMuteStore(kv)
    active = await store.active()
    vids = {a["venue_id"] for a in active}
    assert vids == {"V-live"}
    assert active[0]["by"] == "sam"
    assert await kv.hget(MUTE_KEY, "V-exp") is None
