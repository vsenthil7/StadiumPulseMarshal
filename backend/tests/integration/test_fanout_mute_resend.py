"""Venue fan-out, TZ scheduling, per-venue mute, FAILED resend."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.digest_service import next_run_delay
from app.services.kv_backend import MemoryKV
from app.services.digest_mute_store import DigestMuteStore

PW = "MatchdayDemo123!"


def _resp(c):
    return c.post("/api/v1/auth/login",
                  json={"email": "responder@arena-north.demo", "password": PW}).json()["token"]


# ── CH: timezone-aware ──────────────────────────────────────────────────────
def test_next_run_delay_with_tz():
    import time
    # pick an epoch and confirm tz changes the computed delay vs UTC
    base = 1_700_000_000.0  # fixed instant
    d_utc = next_run_delay("09:00", base, tz="UTC")
    d_tokyo = next_run_delay("09:00", base, tz="Asia/Tokyo")
    assert 0 < d_utc <= 86400 and 0 < d_tokyo <= 86400
    # different local wall-clocks → different delays
    assert d_utc != d_tokyo


def test_next_run_delay_bad_tz_falls_back():
    d = next_run_delay("09:00", 1_700_000_000.0, tz="Not/AZone")
    assert 0 < d <= 86400


# ── CI: mute ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_mute_store_expiry():
    s = DigestMuteStore(MemoryKV())
    await s.mute("venue_x", minutes=0.001, by="a")
    assert await s.is_muted("venue_x") is True
    import time
    time.sleep(0.1)
    assert await s.is_muted("venue_x") is False


def test_mute_suppresses_dispatch():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        c.post("/api/v1/slo/burn-digest/mute",
               json={"venue_id": "venue_arena_north", "minutes": 30}, headers=h)
        r = c.get("/api/v1/slo/burn-digest?venue_id=venue_arena_north&dispatch=true",
                  headers=h).json()
        assert r["dispatched"] is False and r.get("muted") is True
        # unmute restores dispatch
        c.request("DELETE", "/api/v1/slo/burn-digest/mute",
                  params={"venue_id": "venue_arena_north"}, headers=h)
        r2 = c.get("/api/v1/slo/burn-digest?venue_id=venue_arena_north&dispatch=true",
                   headers=h).json()
        assert r2["dispatched"] is True


def test_burn_by_venue_shows_muted():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        c.post("/api/v1/slo/burn-digest/mute",
               json={"venue_id": "venue_arena_north", "minutes": 30}, headers=h)
        rows = c.get("/api/v1/slo/burn-by-venue", headers=h).json()["venues"]
        m = [r for r in rows if r["venue_id"] == "venue_arena_north"]
        assert m and m[0]["muted"] is True


# ── CG: venue fan-out ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_fanout_run_once_routes_and_skips_muted():
    from app.services.digest_service import VenueFanoutScheduler

    sent = []

    async def dispatch(venue_id, recipient, msg):
        sent.append((venue_id, recipient))

    class _Mute:
        async def is_muted(self, v):
            return v == "venue_muted"

    class _Ctx:
        async def burn_alerts(self):
            return []
        class _C:
            async def totals(self, v=None):
                return {"ack": 0, "silence": 0}
        burn_counters = _C()

    sched = VenueFanoutScheduler(
        _Ctx(), 9999,
        {"venue_a": "#a", "venue_muted": "#m"},
        dispatch=dispatch, mute_store=_Mute())
    routed = await sched.run_once()
    assert routed == ["venue_a"]
    assert sent == [("venue_a", "#a")]


# ── CJ: resend ──────────────────────────────────────────────────────────────
def test_resend_failed_digest_flips_to_sent():
    """A digest with no webhook URL records SENT; resend stays SENT and audits."""
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        # dispatch with no webhook configured → stored SENT
        c.get("/api/v1/slo/burn-digest?dispatch=true", headers=h)
        digests = c.get("/api/v1/notifications?severity=digest", headers=h).json()["notifications"]
        assert digests
        nid = digests[0]["id"]
        r = c.post(f"/api/v1/notifications/{nid}/resend", headers=h)
        assert r.status_code == 200
        assert r.json()["status"] == "SENT"


def test_resend_rejects_non_digest():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        r = c.post("/api/v1/notifications/does-not-exist/resend", headers=h)
        assert r.status_code == 404


def test_resend_requires_responder():
    with TestClient(create_app()) as c:
        v = c.post("/api/v1/auth/login",
                   json={"email": "viewer@arena-north.demo", "password": PW}).json()["token"]
        r = c.post("/api/v1/notifications/x/resend",
                   headers={"Authorization": f"Bearer {v}"})
        assert r.status_code == 403
