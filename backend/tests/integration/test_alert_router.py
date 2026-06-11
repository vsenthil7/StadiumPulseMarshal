"""AlertRouter: PagerDuty + OpsGenie delivery via MockTransport."""
from __future__ import annotations

import httpx
import pytest

from app.services.alert_router import AlertRouter
from app.models.notification import (
    Notification, NotificationChannel, NotificationSource,
)


def _notif(channel, severity="page"):
    return Notification(
        id="N-1", incident_id=None, source=NotificationSource.BURN_ALERT,
        severity=severity, channel=channel, recipient="oncall-sre",
        subject="SLO burning", body="payments availability at 14x",
    )


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_pagerduty_page_route():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = req.content.decode()
        return httpx.Response(202, json={"status": "success"})

    r = AlertRouter(pagerduty_routing_key="pdkey", http=_client(handler))
    ok = await r.dispatch(_notif(NotificationChannel.PAGERDUTY))
    assert ok is True
    assert "events.pagerduty.com" in seen["url"]
    assert "pdkey" in seen["body"] and "critical" in seen["body"]


@pytest.mark.asyncio
async def test_opsgenie_fallback_for_non_pd():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(202, json={"result": "created"})

    r = AlertRouter(opsgenie_api_key="ogkey", http=_client(handler))
    ok = await r.dispatch(_notif(NotificationChannel.EMAIL))
    assert ok is True
    assert "api.opsgenie.com" in seen["url"]
    assert seen["auth"] == "GenieKey ogkey"


@pytest.mark.asyncio
async def test_no_credentials_logs_only():
    r = AlertRouter()  # no creds
    ok = await r.dispatch(_notif(NotificationChannel.EMAIL))
    assert ok is False
    assert r.configured is False


@pytest.mark.asyncio
async def test_slack_channel_is_log_ok():
    r = AlertRouter(pagerduty_routing_key="x", http=_client(lambda req: httpx.Response(200)))
    ok = await r.dispatch(_notif(NotificationChannel.SLACK))
    assert ok is True


@pytest.mark.asyncio
async def test_pagerduty_http_error_returns_false():
    r = AlertRouter(pagerduty_routing_key="pdkey",
                    http=_client(lambda req: httpx.Response(500)))
    ok = await r.dispatch(_notif(NotificationChannel.PAGERDUTY))
    assert ok is False
