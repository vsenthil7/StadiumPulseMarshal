"""On-call schedule sources: static, time-rotation, external adapter + fallback."""
from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.models.incident import EscalationTier
from app.models.notification import OnCallEngineer
from app.services.schedule_source import (
    ExternalScheduleSource,
    RotatingScheduleSource,
    StaticScheduleSource,
    _parse_oncalls,
    build_schedule_source,
)


def _eng(eid, tier, handle):
    return OnCallEngineer(id=eid, name=eid, tier=tier, handle=handle, channels=["email"])


@pytest.mark.asyncio
async def test_static_returns_roster():
    roster = [_eng("A", EscalationTier.TIER1, "a@x")]
    src = StaticScheduleSource(roster)
    assert (await src.current_roster())[0].id == "A"


@pytest.mark.asyncio
async def test_rotation_picks_by_shift():
    pool = {EscalationTier.TIER2: [
        _eng("SRE-1", EscalationTier.TIER2, "s1@x"),
        _eng("SRE-2", EscalationTier.TIER2, "s2@x"),
    ]}
    src = RotatingScheduleSource(pools=pool, shift_seconds=3600)
    # shift 0 → SRE-1, shift 1 → SRE-2, shift 2 → SRE-1
    r0 = await src.current_roster(now=0)
    r1 = await src.current_roster(now=3600)
    r2 = await src.current_roster(now=7200)
    assert r0[0].id == "SRE-1"
    assert r1[0].id == "SRE-2"
    assert r2[0].id == "SRE-1"


@pytest.mark.asyncio
async def test_rotation_next_handoff():
    src = RotatingScheduleSource(pools={}, shift_seconds=3600)
    assert src.next_handoff(now=100) == 3600
    assert src.next_handoff(now=3700) == 7200


def test_parse_oncalls_by_escalation_level():
    data = {"oncalls": [
        {"schedule": {"id": "S1"}, "user": {"summary": "Alice", "email": "alice@x"},
         "escalation_level": 1},
        {"schedule": {"id": "S3"}, "user": {"summary": "Carol", "email": "carol@x"},
         "escalation_level": 3},
    ]}
    engs = _parse_oncalls(data, {})
    tiers = {e.tier for e in engs}
    assert EscalationTier.TIER1 in tiers and EscalationTier.TIER3 in tiers
    alice = next(e for e in engs if e.tier == EscalationTier.TIER1)
    assert alice.handle == "alice@x"


def test_parse_oncalls_schedule_tier_map_overrides_level():
    data = {"oncalls": [
        {"schedule": {"id": "SCHED_IC"}, "user": {"summary": "Bob", "email": "bob@x"},
         "escalation_level": 1},
    ]}
    engs = _parse_oncalls(data, {"SCHED_IC": "TIER3"})
    assert engs[0].tier == EscalationTier.TIER3  # map wins over level


@pytest.mark.asyncio
async def test_external_pulls_then_maps():
    settings = Settings(oncall_api_url="https://api.pagerduty.com",
                        oncall_api_token="tok")

    def handler(req):
        assert "/oncalls" in str(req.url)
        return httpx.Response(200, json={"oncalls": [
            {"schedule": {"id": "S2"}, "user": {"summary": "SRE", "email": "sre@x"},
             "escalation_level": 2}]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        src = ExternalScheduleSource(settings, fallback=StaticScheduleSource([]), http=http)
        roster = await src.current_roster()
        assert roster and roster[0].tier == EscalationTier.TIER2
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_external_falls_back_on_error():
    settings = Settings(oncall_api_url="https://api.pagerduty.com",
                        oncall_api_token="tok")
    fallback = StaticScheduleSource([_eng("FB", EscalationTier.TIER1, "fb@x")])

    def handler(req):
        return httpx.Response(500, json={})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        src = ExternalScheduleSource(settings, fallback=fallback, http=http)
        roster = await src.current_roster()
        assert roster[0].id == "FB"
    finally:
        await http.aclose()


def test_build_selects_external_when_configured():
    s = build_schedule_source(
        Settings(oncall_api_url="https://x", oncall_api_token="t"), [])
    assert isinstance(s, ExternalScheduleSource)
    s2 = build_schedule_source(Settings(), [])
    assert isinstance(s2, StaticScheduleSource)


# ── Round 16: rotation pools wired by default ───────────────────────────────
def test_default_pools_rotate_and_build_rotating_source():
    from app.core.config import Settings
    from app.services.ops_defaults import default_oncall_pools, default_on_call
    from app.services.schedule_source import build_schedule_source, RotatingScheduleSource
    src = build_schedule_source(Settings(), default_on_call(), pools=default_oncall_pools())
    assert isinstance(src, RotatingScheduleSource)
    view = src.pool_view(now=0)
    tiers = {r["tier"] for r in view}
    assert {"TIER1", "TIER2", "TIER3"} <= tiers
    # each tier has a current + next with a pool of >= 2
    for r in view:
        assert r["pool_size"] >= 2
        assert r["current"]["name"] != r["next"]["name"]


def test_rotation_disabled_falls_back_to_static():
    from app.core.config import Settings
    from app.services.ops_defaults import default_oncall_pools, default_on_call
    from app.services.schedule_source import build_schedule_source, StaticScheduleSource
    src = build_schedule_source(
        Settings(oncall_rotation_enabled=False), default_on_call(),
        pools=default_oncall_pools())
    assert isinstance(src, StaticScheduleSource)
