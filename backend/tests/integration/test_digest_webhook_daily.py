"""Digest webhook hop, net-active baseline, per-venue suppression, daily digest."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.memory.repositories import MemoryNotificationRepository
from app.services.notification_service import NotificationService

PW = "MatchdayDemo123!"


def _resp(c):
    return c.post("/api/v1/auth/login",
                  json={"email": "responder@arena-north.demo", "password": PW}).json()["token"]


# ── BW: webhook hop ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_notify_digest_posts_to_webhook():
    posted = {}

    async def poster(url, payload):
        posted["url"] = url
        posted["payload"] = payload
        return True

    svc = NotificationService(MemoryNotificationRepository())
    n = await svc.notify_digest("hello digest", recipient="#x",
                                webhook_url="https://hooks.example/abc",
                                webhook_poster=poster)
    assert posted["url"] == "https://hooks.example/abc"
    assert posted["payload"]["text"] == "hello digest"
    assert n.status.value == "SENT"


@pytest.mark.asyncio
async def test_notify_digest_no_url_store_only():
    svc = NotificationService(MemoryNotificationRepository())
    n = await svc.notify_digest("d", recipient="#x")  # no webhook
    assert n.status.value == "SENT"


@pytest.mark.asyncio
async def test_webhook_post_message_retries_then_true():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200 if calls["n"] >= 2 else 500)

    from app.services.webhook_service import WebhookDispatcher, WebhookRepository
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        d = WebhookDispatcher(WebhookRepository(), http, max_attempts=3, base_backoff=0.001)
        ok = await d.post_message("https://x/y", {"text": "hi"})
        assert ok is True and calls["n"] == 2
    finally:
        await http.aclose()


# ── BX: net-active baseline ─────────────────────────────────────────────────
def test_trend_net_active_baseline_from_pre_window():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        a = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if not a:
            return
        x = a[0]
        c.post(f"/api/v1/slo/burn-alerts/{x['slo_id']}/silence",
               json={"severity": x["severity"], "minutes": 30}, headers=h)
        # very small window so the silence is in the pre-window baseline
        body = c.get("/api/v1/slo/burn-trend?hours=0.001&buckets=3", headers=h).json()
        assert "net_active_baseline" in body
        # baseline should reflect the active silence
        assert body["net_active_baseline"] >= 1


# ── BY: per-venue suppression ───────────────────────────────────────────────
def test_burn_by_venue_has_suppression_ratio():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        a = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if a:
            x = a[0]
            c.post(f"/api/v1/slo/burn-alerts/{x['slo_id']}/silence",
                   json={"severity": x["severity"], "minutes": 10}, headers=h)
        rows = c.get("/api/v1/slo/burn-by-venue", headers=h).json()["venues"]
        assert all("suppression_ratio" in r and "ack" in r and "silence" in r for r in rows)


# ── BZ: daily digest ────────────────────────────────────────────────────────
def test_daily_digest_preview():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        r = c.get("/api/v1/slo/burn-digest?kind=daily", headers=h)
        assert r.status_code == 200
        assert "daily burn summary" in r.json()["digest"].lower()
