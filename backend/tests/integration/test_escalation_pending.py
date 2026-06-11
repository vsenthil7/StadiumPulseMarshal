"""Escalation deepening (M2): batch pending re-escalation evaluation."""
from __future__ import annotations
import time
from datetime import datetime, timezone, timedelta

from app.services.escalation_engine import EscalationEngine
from app.models.incident import EscalationTier, Incident, IncidentState
from app.models.notification import EscalationPolicy, EscalationStep, OnCallEngineer
from app.models.enums import Severity


def _engine():
    policy = EscalationPolicy(
        id="default", name="default", min_severity=Severity.LOW,
        steps=[
            EscalationStep(after_minutes=0, tier=EscalationTier.TIER1,
                           notify_channels=["email"]),
            EscalationStep(after_minutes=5, tier=EscalationTier.TIER2,
                           notify_channels=["sms"]),
            EscalationStep(after_minutes=15, tier=EscalationTier.TIER3,
                           notify_channels=["pagerduty"]),
        ])
    oncall = [
        OnCallEngineer(id="e1", name="A", handle="a", tier=EscalationTier.TIER1, channels=["email"]),
        OnCallEngineer(id="e2", name="B", handle="b", tier=EscalationTier.TIER2, channels=["sms"]),
        OnCallEngineer(id="e3", name="C", handle="c", tier=EscalationTier.TIER3, channels=["pagerduty"]),
    ]
    return EscalationEngine([policy], oncall)


def _incident(minutes_ago, tier=EscalationTier.TIER1, state=IncidentState.DETECTED):
    return Incident(
        id="INC-esc", problem_id="P-1", title="DB saturation",
        severity=Severity.CRITICAL, venue_id="venue_arena_north", tier=tier,
        state=state,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))


def test_pending_escalation_fires_after_timeout():
    eng = _engine()
    inc = _incident(20, tier=EscalationTier.TIER1)
    pending = eng.evaluate_pending_escalations([inc], now_seconds=time.time())
    assert len(pending) == 1
    _, decision = pending[0]
    assert decision.should_escalate and decision.target_tier.rank > 1


def test_no_escalation_when_recent():
    eng = _engine()
    inc = _incident(1, tier=EscalationTier.TIER1)
    assert eng.evaluate_pending_escalations([inc], now_seconds=time.time()) == []


def test_closed_incident_skipped():
    eng = _engine()
    inc = _incident(60, tier=EscalationTier.TIER1, state=IncidentState.CLOSED)
    assert eng.evaluate_pending_escalations([inc]) == []


def test_already_top_tier_not_reescalated():
    eng = _engine()
    inc = _incident(60, tier=EscalationTier.TIER3)
    assert eng.evaluate_pending_escalations([inc]) == []
