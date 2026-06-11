"""Per-venue webhooks, scheduler status, mute audit, test-webhook."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PW = "MatchdayDemo123!"


def _tok(c, email):
    return c.post("/api/v1/auth/login",
                  json={"email": email, "password": PW}).json()["token"]


def _resp(c):
    return {"Authorization": f"Bearer {_tok(c, 'responder@arena-north.demo')}"}


def _admin(c):
    return {"Authorization": f"Bearer {_tok(c, 'admin@arena-north.demo')}"}


# ── CL: per-venue webhook resolution ────────────────────────────────────────
def test_webhook_url_for_venue(monkeypatch):
    import app.core.config as cfg
    cfg.get_settings.cache_clear()
    monkeypatch.setenv("BURN_DIGEST_WEBHOOK_URL", "https://global/hook")
    monkeypatch.setenv("BURN_DIGEST_VENUE_WEBHOOKS",
                       "venue_arena_north=https://north/hook")
    try:
        s = cfg.get_settings()
        assert s.webhook_url_for_venue("venue_arena_north") == "https://north/hook"
        assert s.webhook_url_for_venue("venue_other") == "https://global/hook"
        assert s.webhook_url_for_venue(None) == "https://global/hook"
    finally:
        cfg.get_settings.cache_clear()


# ── CM: scheduler status ────────────────────────────────────────────────────
def test_schedulers_status_endpoint():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/ops/schedulers", headers=_admin(c))
        assert r.status_code == 200
        names = {s["name"] for s in r.json()["schedulers"]}
        # prune scheduler always runs
        assert any("prune" in n for n in names)


def test_schedulers_status_requires_admin():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/ops/schedulers",
                  headers={"Authorization": f"Bearer {_tok(c, 'viewer@arena-north.demo')}"})
        assert r.status_code == 403


def test_scheduler_status_shape():
    from app.services.digest_service import DigestScheduler
    s = DigestScheduler(None, 3600)
    st = s.status()
    assert st["name"] == "hourly_digest"
    assert st["running"] is False and st["runs"] == 0
    assert st["next_run_epoch"] is not None


# ── CN: mute audit ──────────────────────────────────────────────────────────
def test_mute_events_history():
    with TestClient(create_app()) as c:
        h = _resp(c)
        c.post("/api/v1/slo/burn-digest/mute",
               json={"venue_id": "venue_arena_north", "minutes": 10}, headers=h)
        c.request("DELETE", "/api/v1/slo/burn-digest/mute",
                  params={"venue_id": "venue_arena_north"}, headers=h)
        ev = c.get("/api/v1/slo/burn-digest/mute-events", headers=h).json()
        actions = {e["action"] for e in ev["events"]}
        assert "mute" in actions and "unmute" in actions


# ── CO: test-webhook ────────────────────────────────────────────────────────
def test_test_webhook_success():
    with TestClient(create_app()) as c:
        import httpx as _h
        ctx = c.app.state.ctx
        ctx.webhook_dispatcher._http = _h.AsyncClient(
            transport=_h.MockTransport(lambda req: _h.Response(200)))
        r = c.post("/api/v1/ops/test-webhook",
                   json={"url": "https://x/y"}, headers=_admin(c))
        assert r.status_code == 200 and r.json()["delivered"] is True


def test_test_webhook_failure():
    with TestClient(create_app()) as c:
        import httpx as _h
        ctx = c.app.state.ctx
        ctx.webhook_dispatcher._http = _h.AsyncClient(
            transport=_h.MockTransport(lambda req: _h.Response(500)))
        ctx.webhook_dispatcher._max_attempts = 1
        r = c.post("/api/v1/ops/test-webhook",
                   json={"url": "https://x/y"}, headers=_admin(c))
        assert r.status_code == 200 and r.json()["delivered"] is False


def test_test_webhook_requires_admin():
    with TestClient(create_app()) as c:
        r = c.post("/api/v1/ops/test-webhook", json={"url": "https://x/y"},
                   headers={"Authorization": f"Bearer {_tok(c, 'viewer@arena-north.demo')}"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_interval_scheduler_records_real_next_wake():
    """Once the loop is sleeping, next_run_epoch reflects the recorded wake time
    rather than a fresh now+interval estimate."""
    import asyncio
    from app.services.digest_service import DigestScheduler

    seen = []

    async def dispatch(msg):
        seen.append(msg)

    class _Ctx:
        async def burn_alerts(self):
            return []
        class _A:
            async def active_summary(self):
                return {"acks": [], "silences": []}
        burn_acks = _A()
        class _C:
            async def totals(self, v=None):
                return {"ack": 0, "silence": 0}
        burn_counters = _C()

    s = DigestScheduler(_Ctx(), 100.0, dispatch=dispatch)
    s.start()
    await asyncio.sleep(0.05)  # let it enter the sleep and set _next_wake
    w1 = s.status()["next_run_epoch"]
    assert w1 is not None
    await asyncio.sleep(0.05)
    w2 = s.status()["next_run_epoch"]
    # recorded wake is stable (not recomputed as now+interval on each read)
    assert w1 == w2
    await s.stop()
