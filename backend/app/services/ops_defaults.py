"""Operational defaults: escalation policies, on-call roster, SLO measurements.

In live deployment these would come from configuration / a roster service. Here
they are sensible defaults so the system is fully operational out of the box.
"""
from __future__ import annotations

from app.models.enums import Severity
from app.models.incident import EscalationTier
from app.models.notification import (
    EscalationPolicy,
    EscalationStep,
    OnCallEngineer,
)
from app.models.slo import SLO, SLOMeasurement


def default_escalation_policies() -> list[EscalationPolicy]:
    return [
        EscalationPolicy(
            id="EP-STANDARD",
            name="Standard (medium+)",
            min_severity=Severity.MEDIUM,
            steps=[
                EscalationStep(tier=EscalationTier.TIER1, after_minutes=0,
                               notify_channels=["email"]),
                EscalationStep(tier=EscalationTier.TIER2, after_minutes=10,
                               notify_channels=["slack"]),
            ],
        ),
        EscalationPolicy(
            id="EP-CRITICAL",
            name="Critical (high+)",
            min_severity=Severity.HIGH,
            steps=[
                EscalationStep(tier=EscalationTier.TIER1, after_minutes=0,
                               notify_channels=["email", "slack"]),
                EscalationStep(tier=EscalationTier.TIER2, after_minutes=5,
                               notify_channels=["sms"]),
                EscalationStep(tier=EscalationTier.TIER3, after_minutes=15,
                               notify_channels=["pagerduty"]),
            ],
        ),
    ]


def default_on_call() -> list[OnCallEngineer]:
    return [
        OnCallEngineer(id="OC-1", name="Venue Ops", tier=EscalationTier.TIER1,
                       handle="venue-ops@tournament.example", channels=["email"]),
        OnCallEngineer(id="OC-2", name="SRE On-Call", tier=EscalationTier.TIER2,
                       handle="sre-oncall@tournament.example",
                       channels=["slack", "sms"]),
        OnCallEngineer(id="OC-3", name="Incident Commander",
                       tier=EscalationTier.TIER3,
                       handle="ic@tournament.example", channels=["pagerduty"]),
    ]


def synthetic_measurement(slo: SLO) -> SLOMeasurement:
    """Derive a plausible SLO measurement from the SLO id.

    Produces a spread of burn states across SLOs (healthy / slow / fast /
    exhausted) so the SLO dashboard is meaningful in mock mode. Deterministic by
    SLO id so values are stable across calls. Uses a 1-hour observation window
    against the SLO's full window for burn-rate computation.
    """
    seed = sum(ord(c) for c in slo.id)
    total = 10000
    allowed = slo.allowed_error_fraction or 0.001
    bucket = seed % 4
    if bucket == 0:
        # fast burn: error rate ~3x the budget-neutral rate
        bad = int(total * allowed * 3.0) + 1
    elif bucket == 1:
        # slow burn: ~1.4x
        bad = int(total * allowed * 1.4) + 1
    elif bucket == 2:
        # healthy: well within budget
        bad = int(total * allowed * 0.3)
    else:
        # exhausted: sustained heavy error over a long observation window
        bad = int(total * allowed * 1.2) + 1
    good = max(0, total - bad)
    # Long observation window for the 'exhausted' bucket pushes consumed >= 1.
    obs_hours = float(slo.window_hours) if bucket == 3 else 1.0
    return SLOMeasurement(
        slo_id=slo.id, good_events=good, total_events=total,
        observation_window_hours=obs_hours,
    )
