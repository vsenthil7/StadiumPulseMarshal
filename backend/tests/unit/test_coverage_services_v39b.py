"""Targeted coverage closeout part B: burn_counters, chatops, alert_router, analytics."""
from __future__ import annotations

import time

import httpx
import pytest

from app.services.kv_backend import MemoryKV
from app.services.burn_counters import BurnCounters, _TOTAL


@pytest.mark.asyncio
async def test_record_ignores_unknown_action():
    c = BurnCounters(MemoryKV())
    await c.record("frobnicate")
    assert await c.any_recorded() is False


@pytest.mark.asyncio
async def test_totals_ignores_non_digit_and_unknown_action_fields():
    kv = MemoryKV()
    await kv.hset(_TOTAL, "ack", "3")
    await kv.hset(_TOTAL, "bogus", "not-an-int")
    await kv.hset(_TOTAL, "unknownaction", "5")
    c = BurnCounters(kv)
    totals = await c.totals()
    assert totals["ack"] == 3
    assert totals["silence"] == 0


@pytest.mark.asyncio
async def test_totals_venue_filter():
    c = BurnCounters(MemoryKV())
    await c.record("ack", "V-A")
    await c.record("ack", "V-B")
    a = await c.totals("V-A")
    assert a["ack"] == 1
    # record() also increments the venue-less field each call, so global == 2
    glob = await c.totals()
    assert glob["ack"] == 2


@pytest.mark.asyncio
async def test_buckets_venue_filter_and_since():
    c = BurnCounters(MemoryKV())
    now = time.time()
    await c.record("ack", "V-A", at=now)
    await c.record("silence", at=now)
    b_va = await c.buckets(0, "V-A")
    assert any(v["ack"] == 1 for v in b_va.values())
    b_glob = await c.buckets(0)
    assert any(v["silence"] == 1 for v in b_glob.values())
    assert await c.buckets(now + 10_000) == {}


@pytest.mark.asyncio
async def test_buckets_ignores_malformed_fields():
    kv = MemoryKV()
    from app.services.burn_counters import _BUCKET
    await kv.hset(_BUCKET, "not-a-bucket", "1")
    await kv.hset(_BUCKET, "1700000000:ack", "nope")
    await kv.hset(_BUCKET, "single", "1")
    c = BurnCounters(kv)
    assert await c.buckets(0) == {}


def test_slack_command_model_defaults():
    from app.models.chatops import SlackCommand
    cmd = SlackCommand(command="/spm")
    assert cmd.command == "/spm"
    assert cmd.text == "" and cmd.user_id == ""
    full = SlackCommand(command="/spm", text="status", user_id="U1",
                        user_name="sam", channel_id="C1", response_url="http://x")
    assert full.user_name == "sam" and full.channel_id == "C1"


def _notif(channel, severity="page", **kw):
    from app.models.notification import Notification
    return Notification(
        id="N-1", channel=channel, recipient="oncall",
        subject="DB saturation", body="payments db at 95%",
        severity=severity, incident_id="INC-1", venue_id="V-1", **kw,
    )


@pytest.mark.asyncio
async def test_alert_router_no_credentials_returns_false():
    from app.services.alert_router import AlertRouter
    from app.models.notification import NotificationChannel
    r = AlertRouter()
    assert r.configured is False
    assert await r.dispatch(_notif(NotificationChannel.PAGERDUTY)) is False
    await r.close()


@pytest.mark.asyncio
async def test_alert_router_slack_logs_true():
    from app.services.alert_router import AlertRouter
    from app.models.notification import NotificationChannel
    r = AlertRouter()
    assert await r.dispatch(_notif(NotificationChannel.SLACK)) is True
    await r.close()


@pytest.mark.asyncio
async def test_alert_router_pagerduty_success_and_failure():
    from app.services.alert_router import AlertRouter
    from app.models.notification import NotificationChannel

    def handler(request):
        return httpx.Response(202, json={"status": "queued"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        r = AlertRouter(pagerduty_routing_key="pd-key", http=http)
        assert r.configured is True
        assert await r.dispatch(_notif(NotificationChannel.PAGERDUTY)) is True

    def fail_handler(request):
        return httpx.Response(500, json={"error": "boom"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail_handler)) as http:
        r2 = AlertRouter(pagerduty_routing_key="pd-key", http=http)
        assert await r2.dispatch(_notif(NotificationChannel.PAGERDUTY)) is False


@pytest.mark.asyncio
async def test_alert_router_pagerduty_exception_returns_false():
    from app.services.alert_router import AlertRouter
    from app.models.notification import NotificationChannel

    def boom(request):
        raise httpx.ConnectError("network down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
        r = AlertRouter(pagerduty_routing_key="pd-key", http=http)
        assert await r.dispatch(_notif(NotificationChannel.PAGERDUTY)) is False


@pytest.mark.asyncio
async def test_alert_router_opsgenie_secondary_path():
    from app.services.alert_router import AlertRouter
    from app.models.notification import NotificationChannel

    captured = {}

    def handler(request):
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(201, json={"result": "created"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        r = AlertRouter(opsgenie_api_key="og-key", http=http)
        assert await r.dispatch(_notif(NotificationChannel.EMAIL, severity="page")) is True
        assert captured["auth"] == "GenieKey og-key"


@pytest.mark.asyncio
async def test_alert_router_opsgenie_failure_and_exception():
    from app.services.alert_router import AlertRouter
    from app.models.notification import NotificationChannel

    def fail(request):
        return httpx.Response(403, json={"error": "denied"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http:
        r = AlertRouter(opsgenie_api_key="og-key", http=http)
        assert await r.dispatch(_notif(NotificationChannel.EMAIL, severity="ticket")) is False

    def boom(request):
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
        r2 = AlertRouter(opsgenie_api_key="og-key", http=http)
        assert await r2.dispatch(_notif(NotificationChannel.EMAIL)) is False


def test_build_alert_router_from_settings():
    from app.services.alert_router import build_alert_router

    class _S:
        pagerduty_routing_key = "pd"
        opsgenie_api_key = None

    assert build_alert_router(_S()).configured is True


def _incident(state_value, severity_value, venue, ttr=None, tta=None):
    class _Enum:
        def __init__(self, v): self.value = v

    class _Inc:
        pass

    inc = _Inc()
    inc.state = _Enum(state_value)
    inc.severity = _Enum(severity_value)
    inc.venue_id = venue
    inc.ttr_minutes = ttr
    inc.tta_minutes = tta
    inc.is_open = state_value not in ("RESOLVED", "CLOSED")
    return inc


def _budget(breaching):
    class _B:
        is_breaching = breaching
    return _B()


def test_compute_summary_mttr_mtta_and_breaches():
    from app.services.analytics import compute_summary
    incidents = [
        _incident("RESOLVED", "SEV1", "V-A", ttr=30.0, tta=5.0),
        _incident("INVESTIGATING", "SEV2", "V-B"),
        _incident("RESOLVED", "SEV1", None, ttr=10.0, tta=15.0),
    ]
    s = compute_summary(incidents, [_budget(True), _budget(False)])
    assert s.total_incidents == 3
    assert s.resolved_incidents == 2 and s.open_incidents == 1
    assert s.mttr_minutes == 20.0
    assert s.mtta_minutes == 10.0
    assert s.by_severity["SEV1"] == 2
    assert s.by_venue["V-A"] == 1 and "V-B" in s.by_venue
    assert s.slo_total == 2 and s.slo_breaching == 1


def test_compute_summary_empty_means_none():
    from app.services.analytics import compute_summary
    s = compute_summary([], [])
    assert s.mttr_minutes is None and s.mtta_minutes is None


def test_compute_by_venue_health():
    from app.services.analytics import compute_by_venue
    incidents = [
        _incident("RESOLVED", "SEV1", "V-A", ttr=20.0, tta=4.0),
        _incident("OPEN", "SEV2", "V-A"),
        _incident("RESOLVED", "SEV3", "V-B", ttr=8.0, tta=2.0),
    ]
    budgets_by_venue = {"V-A": [_budget(True), _budget(False)], "V-B": []}
    out = compute_by_venue(incidents, budgets_by_venue, ["V-A", "V-B"])
    va = next(v for v in out if v.venue_id == "V-A")
    vb = next(v for v in out if v.venue_id == "V-B")
    assert va.total_incidents == 2 and va.open_incidents == 1
    assert va.mttr_minutes == 20.0 and va.mtta_minutes == 4.0
    assert va.slo_total == 2 and va.slo_breaching == 1
    assert va.slo_health == 50.0
    assert vb.slo_total == 0 and vb.slo_health == 100.0

