"""On-call, escalation-policy and notification domain models."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .enums import Severity
from .incident import EscalationTier


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OnCallEngineer(BaseModel):
    """An engineer who can be assigned/paged at a given tier."""

    id: str
    name: str
    tier: EscalationTier
    handle: str = ""
    channels: list[str] = Field(default_factory=list)  # e.g. ["email", "sms"]


class EscalationStep(BaseModel):
    """One rung of an escalation policy."""

    tier: EscalationTier
    after_minutes: float = Field(ge=0)
    notify_channels: list[str] = Field(default_factory=list)


class EscalationPolicy(BaseModel):
    """An ordered escalation policy keyed by minimum severity."""

    id: str
    name: str
    min_severity: Severity = Severity.MEDIUM
    steps: list[EscalationStep] = Field(default_factory=list)

    def step_for_elapsed(self, elapsed_minutes: float) -> EscalationStep | None:
        """Return the highest step whose threshold has elapsed."""
        applicable = [s for s in self.steps if elapsed_minutes >= s.after_minutes]
        if not applicable:
            return None
        return max(applicable, key=lambda s: s.after_minutes)


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


class NotificationStatus(str, Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"


class NotificationSource(str, Enum):
    INCIDENT = "incident"
    BURN_ALERT = "burn_alert"


class Notification(BaseModel):
    """A notification dispatched (or queued).

    Originally incident-bound; now ``incident_id`` is optional so notifications
    can originate from other sources (e.g. SLO burn-rate alerts). ``source`` and
    ``severity`` let the UI group/colour them and let routing pick a channel.
    """

    id: str
    incident_id: str | None = None
    source: NotificationSource = NotificationSource.INCIDENT
    severity: str = ""
    venue_id: str | None = None
    channel: NotificationChannel
    recipient: str
    subject: str
    body: str
    status: NotificationStatus = NotificationStatus.QUEUED
    created_at: datetime = Field(default_factory=_utcnow)
    sent_at: datetime | None = None
