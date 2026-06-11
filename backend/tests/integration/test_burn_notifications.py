"""Burn-alert → notification routing (channel policy + dedupe)."""
from __future__ import annotations

import pytest

from app.models.notification import NotificationChannel, NotificationSource
from app.models.slo import BurnAlert, BurnSeverity
from app.repositories.memory.repositories import MemoryNotificationRepository
from app.services.notification_service import NotificationService


def _alert(severity: BurnSeverity, slo_id="SLO-X", short_h=5 / 60):
    return BurnAlert(
        slo_id=slo_id, slo_name="Payments availability", service_id="SVC-PAYMENTS",
        venue_id="venue_arena_north", severity=severity, burn_rate=14.4,
        long_window_hours=1.0, short_window_hours=short_h, factor=14.4,
        error_budget_consumed_pct=2.0, message="fast burn",
    )


@pytest.mark.asyncio
async def test_page_routes_to_pagerduty_and_sms():
    svc = NotificationService(MemoryNotificationRepository())
    created = await svc.notify_burn_alert(_alert(BurnSeverity.PAGE))
    channels = {n.channel for n in created}
    assert NotificationChannel.PAGERDUTY in channels
    assert NotificationChannel.SMS in channels
    assert all(n.source == NotificationSource.BURN_ALERT for n in created)
    assert all(n.incident_id is None for n in created)
    assert all(n.severity == "page" for n in created)


@pytest.mark.asyncio
async def test_ticket_routes_to_email_and_slack():
    svc = NotificationService(MemoryNotificationRepository())
    created = await svc.notify_burn_alert(_alert(BurnSeverity.TICKET))
    channels = {n.channel for n in created}
    assert channels == {NotificationChannel.EMAIL, NotificationChannel.SLACK}


@pytest.mark.asyncio
async def test_dedupe_within_window():
    svc = NotificationService(MemoryNotificationRepository())
    first = await svc.notify_burn_alert(_alert(BurnSeverity.PAGE, short_h=1.0))
    assert first  # sent
    # second identical alert within the window → suppressed
    second = await svc.notify_burn_alert(_alert(BurnSeverity.PAGE, short_h=1.0))
    assert second == []


@pytest.mark.asyncio
async def test_distinct_slos_not_deduped():
    svc = NotificationService(MemoryNotificationRepository())
    await svc.notify_burn_alert(_alert(BurnSeverity.PAGE, slo_id="SLO-A"))
    other = await svc.notify_burn_alert(_alert(BurnSeverity.PAGE, slo_id="SLO-B"))
    assert other  # different SLO → not suppressed


@pytest.mark.asyncio
async def test_none_severity_routes_nowhere():
    svc = NotificationService(MemoryNotificationRepository())
    assert await svc.notify_burn_alert(_alert(BurnSeverity.NONE)) == []


@pytest.mark.asyncio
async def test_notifications_filter_by_source_via_api():
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as c:
        tok = c.post("/api/v1/auth/login",
                     json={"email": "sre@stadiumpulse.demo",
                           "password": "MatchdayDemo123!"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        # trigger burn alerts → burn-sourced notifications
        c.get("/api/v1/slo/burn-alerts", headers=h)
        alln = c.get("/api/v1/notifications", headers=h).json()["notifications"]
        burn = c.get("/api/v1/notifications?source=burn_alert", headers=h).json()["notifications"]
        assert burn and all(n["source"] == "burn_alert" for n in burn)
        assert len(burn) <= len(alln)
