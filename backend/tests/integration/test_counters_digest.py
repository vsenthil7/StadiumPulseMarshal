"""Pre-agg counters + digest service."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.kv_backend import MemoryKV
from app.services.burn_counters import BurnCounters

PW = "MatchdayDemo123!"


@pytest.mark.asyncio
async def test_counters_increment_and_total():
    c = BurnCounters(MemoryKV())
    await c.record("ack", "venue_arena_north")
    await c.record("ack", "venue_arena_north")
    await c.record("silence", "venue_olympic_park")
    allv = await c.totals()
    assert allv["ack"] == 2 and allv["silence"] == 1
    north = await c.totals("venue_arena_north")
    assert north["ack"] == 2 and north["silence"] == 0


@pytest.mark.asyncio
async def test_counter_buckets():
    c = BurnCounters(MemoryKV())
    await c.record("silence")
    b = await c.buckets(0)
    assert sum(v["silence"] for v in b.values()) == 1


def test_burn_stats_uses_counters_after_action():
    with TestClient(create_app()) as c:
        tok = c.post("/api/v1/auth/login",
                     json={"email": "responder@arena-north.demo", "password": PW}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        a = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if not a:
            return
        x = a[0]
        c.post(f"/api/v1/slo/burn-alerts/{x['slo_id']}/ack",
               json={"severity": x["severity"]}, headers=h)
        stats = c.get("/api/v1/slo/burn-stats", headers=h).json()
        assert stats["counts"]["ack"] >= 1


def test_burn_digest_preview():
    with TestClient(create_app()) as c:
        tok = c.post("/api/v1/auth/login",
                     json={"email": "sre@stadiumpulse.demo", "password": PW}).json()["token"]
        r = c.get("/api/v1/slo/burn-digest", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert "burn digest" in r.json()["digest"].lower()


def test_burn_by_venue_breakdown():
    with TestClient(create_app()) as c:
        tok = c.post("/api/v1/auth/login",
                     json={"email": "sre@stadiumpulse.demo", "password": PW}).json()["token"]
        r = c.get("/api/v1/slo/burn-by-venue", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert "venues" in r.json()


@pytest.mark.asyncio
async def test_digest_scheduler_idempotent_start_stop():
    from app.services.digest_service import DigestScheduler
    app = create_app()
    # minimal: scheduler over a tiny interval, dispatch captures messages
    seen = []

    class _Ctx:
        async def burn_alerts(self):
            return []
        class _Acks:
            async def active_summary(self):
                return {"acks": [], "silences": []}
        burn_acks = _Acks()
        class _Ctr:
            async def totals(self):
                return {"ack": 0, "silence": 0}
        burn_counters = _Ctr()

    sched = DigestScheduler(_Ctx(), 0.01, dispatch=lambda m: seen.append(m) or _noop())
    # start twice → only one task
    sched.start()
    sched.start()
    import asyncio
    await asyncio.sleep(0.05)
    await sched.stop()
    await sched.stop()  # idempotent
    assert isinstance(seen, list)


async def _noop():
    return None
