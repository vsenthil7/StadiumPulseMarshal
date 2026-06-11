"""Burn-alert routing via the on-call directory (real roster handles/channels)."""
from __future__ import annotations

import pytest

from app.models.incident import EscalationTier
from app.models.slo import BurnAlert, BurnSeverity
from app.services.oncall_directory import OnCallDirectory
from app.services.ops_defaults import default_on_call
from app.services.notification_service import NotificationService
from app.repositories.memory.repositories import MemoryNotificationRepository


def _alert(sev):
    return BurnAlert(
        slo_id="SLO-X", slo_name="Payments", service_id="SVC-PAYMENTS",
        venue_id="venue_arena_north", severity=sev, burn_rate=14.4,
        long_window_hours=1.0, short_window_hours=5/60, factor=14.4,
        error_budget_consumed_pct=2.0, message="burn",
    )


def test_directory_resolves_page_to_ic_and_sre():
    d = OnCallDirectory(default_on_call())
    targets = d.targets_for_severity("page")
    tiers = [t.tier for t in targets]
    assert EscalationTier.TIER3 in tiers   # incident commander
    assert EscalationTier.TIER2 in tiers   # SRE
    # IC's real handle is used
    ic = next(t for t in targets if t.tier == EscalationTier.TIER3)
    assert "ic@" in ic.recipient


def test_directory_resolves_ticket_to_sre_and_venueops():
    d = OnCallDirectory(default_on_call())
    targets = d.targets_for_severity("ticket")
    tiers = {t.tier for t in targets}
    assert EscalationTier.TIER2 in tiers and EscalationTier.TIER1 in tiers


@pytest.mark.asyncio
async def test_notify_routes_through_directory_real_handles():
    svc = NotificationService(MemoryNotificationRepository(),
                              oncall_directory=OnCallDirectory(default_on_call()))
    created = await svc.notify_burn_alert(_alert(BurnSeverity.PAGE))
    recipients = {n.recipient for n in created}
    # IC + SRE real handles, not the static "oncall-sre"/phone placeholders
    assert any("ic@" in r for r in recipients)
    assert any("sre-oncall@" in r for r in recipients)


@pytest.mark.asyncio
async def test_fallback_to_static_without_directory():
    svc = NotificationService(MemoryNotificationRepository())  # no directory
    created = await svc.notify_burn_alert(_alert(BurnSeverity.TICKET))
    # static policy: email + slack
    channels = {n.channel.value for n in created}
    assert channels == {"email", "slack"}


def test_directory_fallback_when_tier_vacant():
    # roster missing TIER3 → page still resolves to the next available tier
    from app.models.notification import OnCallEngineer
    roster = [OnCallEngineer(id="OC-2", name="SRE", tier=EscalationTier.TIER2,
                             handle="sre@x", channels=["slack"])]
    d = OnCallDirectory(roster)
    targets = d.targets_for_severity("page")
    assert targets and targets[0].tier == EscalationTier.TIER2


def test_oncall_endpoint_returns_roster_policies_targets():
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as c:
        tok = c.post("/api/v1/auth/login",
                     json={"email": "operator@arena-north.demo",
                           "password": "MatchdayDemo123!"}).json()["token"]
        r = c.get("/api/v1/oncall", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        body = r.json()
        assert len(body["roster"]) >= 3
        assert len(body["policies"]) >= 2
        assert "page" in body["burn_targets"] and "ticket" in body["burn_targets"]
        # page targets include the incident commander
        assert any(t["tier"] == "TIER3" for t in body["burn_targets"]["page"])
