"""Tests for Phase 2 domain models."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.incident import (
    EscalationTier,
    Incident,
    IncidentEvent,
    IncidentEventType,
    IncidentState,
    can_transition,
)
from app.models.notification import (
    EscalationPolicy,
    EscalationStep,
    Notification,
    NotificationChannel,
    NotificationStatus,
    OnCallEngineer,
)
from app.models.slo import (
    SLI,
    SLO,
    BurnState,
    ErrorBudget,
    SLIKind,
    SLOMeasurement,
)
from app.models.venue import Match, MatchdayContext, Venue
from app.models.enums import Severity


def test_slo_allowed_error_and_measurement():
    sli = SLI(key="a", kind=SLIKind.AVAILABILITY, entity_id="SVC")
    slo = SLO(id="S", name="n", service_id="SVC", sli=sli, target=0.99)
    assert round(slo.allowed_error_fraction, 4) == 0.01
    m = SLOMeasurement(slo_id="S", good_events=99, total_events=100)
    assert m.achieved == 0.99
    assert m.bad_events == 1
    empty = SLOMeasurement(slo_id="S", good_events=0, total_events=0)
    assert empty.achieved == 1.0


def test_burn_state_rank():
    assert BurnState.HEALTHY.rank < BurnState.EXHAUSTED.rank


def test_error_budget_breaching():
    b = ErrorBudget(slo_id="S", slo_name="n", target=0.99, achieved=0.95,
                    consumed_fraction=5.0, remaining_fraction=0.0,
                    burn_rate=5.0, state=BurnState.EXHAUSTED)
    assert b.is_breaching is True


def test_incident_transitions_map():
    assert can_transition(IncidentState.DETECTED, IncidentState.INVESTIGATING)
    assert not can_transition(IncidentState.CLOSED, IncidentState.DETECTED)
    assert not can_transition(IncidentState.RESOLVED, IncidentState.DETECTED)


def test_escalation_tier_next_and_rank():
    assert EscalationTier.TIER1.next_tier() == EscalationTier.TIER2
    assert EscalationTier.TIER3.next_tier() == EscalationTier.TIER3  # capped
    assert EscalationTier.TIER2.rank == 2


def test_incident_ttr_tta_and_open():
    now = datetime.now(timezone.utc)
    inc = Incident(id="I", problem_id="P", title="t", severity=Severity.HIGH,
                   created_at=now - timedelta(minutes=20))
    assert inc.ttr_minutes is None
    assert inc.tta_minutes is None
    assert inc.is_open is True
    inc.acknowledged_at = now - timedelta(minutes=15)
    inc.resolved_at = now
    assert round(inc.ttr_minutes) == 20
    assert round(inc.tta_minutes) == 5
    inc.add_event(IncidentEvent(type=IncidentEventType.NOTE, detail="x"))
    assert len(inc.timeline) == 1


def test_escalation_policy_step_for_elapsed():
    pol = EscalationPolicy(id="P", name="n", steps=[
        EscalationStep(tier=EscalationTier.TIER1, after_minutes=0),
        EscalationStep(tier=EscalationTier.TIER2, after_minutes=5),
    ])
    assert pol.step_for_elapsed(0).tier == EscalationTier.TIER1
    assert pol.step_for_elapsed(6).tier == EscalationTier.TIER2
    empty = EscalationPolicy(id="P", name="n", steps=[
        EscalationStep(tier=EscalationTier.TIER1, after_minutes=10)])
    assert empty.step_for_elapsed(0) is None


def test_oncall_and_notification():
    eng = OnCallEngineer(id="E", name="Sam", tier=EscalationTier.TIER2,
                         handle="sam", channels=["sms"])
    assert eng.tier == EscalationTier.TIER2
    n = Notification(id="N", incident_id="I", channel=NotificationChannel.SMS,
                     recipient="sam", subject="s", body="b")
    assert n.status == NotificationStatus.QUEUED


def test_venue_and_match():
    v = Venue(id="V", name="MetLife", city="ER", country="USA", capacity=82500)
    m = Match(id="M", venue_id="V", home="ARG", away="BRA",
              kickoff=datetime.now(timezone.utc))
    assert m.label == "ARG vs BRA"
    ctx = MatchdayContext(venue=v, match=m)
    assert ctx.venue.capacity == 82500
