"""Incident domain models and lifecycle state machine.

An Incident wraps the operational response around a Dynatrace Problem: it has a
lifecycle, an assignee, an escalation tier, a timeline of events, and links to
remediation actions. The allowed transitions are enforced by
``INCIDENT_TRANSITIONS`` and validated in the incident service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .enums import Severity


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IncidentState(str, Enum):
    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    MITIGATING = "MITIGATING"
    RESOLVED = "RESOLVED"
    POSTMORTEM = "POSTMORTEM"
    CLOSED = "CLOSED"


# Allowed state transitions (directed graph).
INCIDENT_TRANSITIONS: dict[IncidentState, set[IncidentState]] = {
    IncidentState.DETECTED: {
        IncidentState.ACKNOWLEDGED,
        IncidentState.INVESTIGATING,
    },
    IncidentState.ACKNOWLEDGED: {
        IncidentState.INVESTIGATING,
        IncidentState.RESOLVED,
    },
    IncidentState.INVESTIGATING: {
        IncidentState.MITIGATING,
        IncidentState.RESOLVED,
    },
    IncidentState.MITIGATING: {
        IncidentState.RESOLVED,
        IncidentState.INVESTIGATING,
    },
    IncidentState.RESOLVED: {
        IncidentState.POSTMORTEM,
        IncidentState.CLOSED,
        IncidentState.INVESTIGATING,  # reopen
    },
    IncidentState.POSTMORTEM: {IncidentState.CLOSED},
    IncidentState.CLOSED: set(),
}


def can_transition(src: IncidentState, dst: IncidentState) -> bool:
    return dst in INCIDENT_TRANSITIONS.get(src, set())


class EscalationTier(str, Enum):
    TIER1 = "TIER1"   # first responder / venue ops
    TIER2 = "TIER2"   # service owner / SRE
    TIER3 = "TIER3"   # incident commander / tournament ops lead

    @property
    def rank(self) -> int:
        return {"TIER1": 1, "TIER2": 2, "TIER3": 3}[self.value]

    def next_tier(self) -> "EscalationTier":
        order = [EscalationTier.TIER1, EscalationTier.TIER2, EscalationTier.TIER3]
        idx = min(order.index(self) + 1, len(order) - 1)
        return order[idx]


class IncidentEventType(str, Enum):
    CREATED = "CREATED"
    STATE_CHANGE = "STATE_CHANGE"
    ASSIGNED = "ASSIGNED"
    ESCALATED = "ESCALATED"
    NOTE = "NOTE"
    REMEDIATION_PROPOSED = "REMEDIATION_PROPOSED"
    REMEDIATION_APPROVED = "REMEDIATION_APPROVED"
    REMEDIATION_REJECTED = "REMEDIATION_REJECTED"
    REMEDIATION_EXECUTED = "REMEDIATION_EXECUTED"
    NOTIFICATION_SENT = "NOTIFICATION_SENT"


class IncidentEvent(BaseModel):
    """A single entry on the incident timeline."""

    type: IncidentEventType
    at: datetime = Field(default_factory=_utcnow)
    actor: str = "system"
    detail: str = ""
    data: dict = Field(default_factory=dict)


class Incident(BaseModel):
    """Operational incident wrapping a detected problem."""

    id: str
    problem_id: str
    title: str
    severity: Severity
    state: IncidentState = IncidentState.DETECTED
    tier: EscalationTier = EscalationTier.TIER1
    assignee: str | None = None
    venue_id: str | None = None
    match_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    timeline: list[IncidentEvent] = Field(default_factory=list)
    remediation_ids: list[str] = Field(default_factory=list)
    impact_summary: str = ""

    @property
    def is_open(self) -> bool:
        return self.state not in (IncidentState.RESOLVED, IncidentState.CLOSED)

    @property
    def ttr_minutes(self) -> float | None:
        """Time-to-resolve in minutes, if resolved."""
        if self.resolved_at is None:
            return None
        return (self.resolved_at - self.created_at).total_seconds() / 60.0

    @property
    def tta_minutes(self) -> float | None:
        """Time-to-acknowledge in minutes, if acknowledged."""
        if self.acknowledged_at is None:
            return None
        return (self.acknowledged_at - self.created_at).total_seconds() / 60.0

    def add_event(self, event: IncidentEvent) -> None:
        self.timeline.append(event)
