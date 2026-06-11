"""Tests for incident-service escalation dispatch and notification service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.domain import Problem
from app.models.enums import ProblemStatus, Severity
from app.models.incident import (
    EscalationTier,
    IncidentEventType,
    IncidentState,
)
from app.models.notification import (
    EscalationPolicy,
    EscalationStep,
    NotificationChannel,
    OnCallEngineer,
)
from app.repositories.memory.repositories import (
    MemoryIncidentRepository,
    MemoryNotificationRepository,
)
from app.services.escalation_engine import EscalationEngine
from app.services.incident_service import IncidentError, IncidentService
from app.services.notification_service import NotificationService


def _problem(sev=Severity.CRITICAL) -> Problem:
    return Problem(id="P-1", title="Outage", severity=sev,
                   status=ProblemStatus.OPEN, impact_summary="bad")


def _service_with_oncall(channels):
    inc_repo = MemoryIncidentRepository()
    ntf = NotificationService(MemoryNotificationRepository())
    policy = EscalationPolicy(
        id="EP", name="crit", min_severity=Severity.HIGH,
        steps=[
            EscalationStep(tier=EscalationTier.TIER1, after_minutes=0),
            EscalationStep(tier=EscalationTier.TIER2, after_minutes=5,
                           notify_channels=channels),
        ],
    )
    oncall = [OnCallEngineer(id="E2", name="Sam", tier=EscalationTier.TIER2,
                             handle="sam@ops", channels=["email"])]
    esc = EscalationEngine([policy], oncall)
    return IncidentService(inc_repo, esc, ntf), inc_repo, ntf


async def test_escalation_dispatches_notifications():
    svc, inc_repo, ntf = _service_with_oncall(["sms"])
    inc = await svc.create_from_problem(_problem(), venue_id="V")
    # age the incident past the 5-minute step
    inc.created_at = datetime.now(timezone.utc) - timedelta(minutes=7)
    await inc_repo.update(inc)
    updated = await svc.evaluate_escalation(inc.id)
    assert updated.tier == EscalationTier.TIER2
    notifs = await ntf.list_for_incident(inc.id)
    assert len(notifs) == 1
    assert notifs[0].channel == NotificationChannel.SMS
    # timeline has ESCALATED + NOTIFICATION_SENT
    types = {e.type for e in updated.timeline}
    assert IncidentEventType.ESCALATED in types
    assert IncidentEventType.NOTIFICATION_SENT in types


async def test_escalation_unknown_channel_defaults_email():
    svc, inc_repo, ntf = _service_with_oncall(["carrier-pigeon"])
    inc = await svc.create_from_problem(_problem())
    inc.created_at = datetime.now(timezone.utc) - timedelta(minutes=7)
    await inc_repo.update(inc)
    await svc.evaluate_escalation(inc.id)
    notifs = await ntf.list_for_incident(inc.id)
    assert notifs[0].channel == NotificationChannel.EMAIL


async def test_escalation_uses_engineer_channels_when_step_has_none():
    inc_repo = MemoryIncidentRepository()
    ntf = NotificationService(MemoryNotificationRepository())
    policy = EscalationPolicy(
        id="EP", name="crit", min_severity=Severity.HIGH,
        steps=[EscalationStep(tier=EscalationTier.TIER2, after_minutes=0)],
    )
    oncall = [OnCallEngineer(id="E2", name="Sam", tier=EscalationTier.TIER2,
                             handle="sam", channels=["slack"])]
    svc = IncidentService(inc_repo, EscalationEngine([policy], oncall), ntf)
    inc = await svc.create_from_problem(_problem())
    updated = await svc.evaluate_escalation(inc.id)
    assert updated.tier == EscalationTier.TIER2
    notifs = await ntf.list_for_incident(inc.id)
    assert notifs[0].channel == NotificationChannel.SLACK


async def test_escalation_no_engineer_no_notification():
    inc_repo = MemoryIncidentRepository()
    ntf = NotificationService(MemoryNotificationRepository())
    policy = EscalationPolicy(
        id="EP", name="crit", min_severity=Severity.HIGH,
        steps=[EscalationStep(tier=EscalationTier.TIER3, after_minutes=0)],
    )
    # no TIER3 engineer registered
    svc = IncidentService(inc_repo, EscalationEngine([policy], []), ntf)
    inc = await svc.create_from_problem(_problem())
    updated = await svc.evaluate_escalation(inc.id)
    assert updated.tier == EscalationTier.TIER3
    assert len(await ntf.list_for_incident(inc.id)) == 0


async def test_escalation_no_change_when_not_due():
    svc, inc_repo, ntf = _service_with_oncall(["sms"])
    inc = await svc.create_from_problem(_problem())
    # fresh incident: only TIER1 step due, equal to current tier -> no escalate
    updated = await svc.evaluate_escalation(inc.id)
    assert updated.tier == EscalationTier.TIER1
    assert len(await ntf.list_for_incident(inc.id)) == 0


async def test_link_remediation_and_missing():
    svc, _, _ = _service_with_oncall(["sms"])
    inc = await svc.create_from_problem(_problem())
    updated = await svc.link_remediation(
        inc.id, "RA-1", IncidentEventType.REMEDIATION_APPROVED,
        actor="jane", detail="approved")
    assert "RA-1" in updated.remediation_ids
    # linking same id again doesn't duplicate
    again = await svc.link_remediation(
        inc.id, "RA-1", IncidentEventType.REMEDIATION_EXECUTED)
    assert again.remediation_ids.count("RA-1") == 1
    with pytest.raises(IncidentError):
        await svc.transition("MISSING", IncidentState.ACKNOWLEDGED)


async def test_notification_service_list_all():
    ntf = NotificationService(MemoryNotificationRepository())
    svc, inc_repo, _ = _service_with_oncall(["sms"])
    inc = await svc.create_from_problem(_problem())
    n = await ntf.notify(inc, channel=NotificationChannel.EMAIL,
                         recipient="a@b", subject="s", body="b")
    assert n.status.value == "SENT"
    assert n.sent_at is not None
    assert len(await ntf.list_all()) == 1
