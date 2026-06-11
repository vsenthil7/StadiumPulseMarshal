"""Escalation engine: applies escalation policies and routes to on-call.

Given an incident's age and severity, determines the correct escalation tier per
policy and resolves the on-call engineer to page. Pure logic; the incident
service consumes its decisions and the notification service delivers them.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.models.incident import EscalationTier, Incident
from app.models.notification import EscalationPolicy, OnCallEngineer

log = get_logger(__name__)


class EscalationDecision:
    """The outcome of evaluating escalation for an incident."""

    def __init__(
        self,
        should_escalate: bool,
        target_tier: EscalationTier,
        engineer: OnCallEngineer | None,
        channels: list[str],
    ) -> None:
        self.should_escalate = should_escalate
        self.target_tier = target_tier
        self.engineer = engineer
        self.channels = channels


class EscalationEngine:
    def __init__(
        self,
        policies: list[EscalationPolicy],
        on_call: list[OnCallEngineer],
    ) -> None:
        self._policies = policies
        self._on_call = on_call

    def policy_for(self, incident: Incident) -> EscalationPolicy | None:
        """Pick the policy whose min severity the incident meets, most specific."""
        applicable = [
            p
            for p in self._policies
            if incident.severity.rank >= p.min_severity.rank
        ]
        if not applicable:
            return None
        return max(applicable, key=lambda p: p.min_severity.rank)

    def on_call_for(self, tier: EscalationTier) -> OnCallEngineer | None:
        for eng in self._on_call:
            if eng.tier == tier:
                return eng
        return None

    def evaluate(
        self, incident: Incident, elapsed_minutes: float
    ) -> EscalationDecision:
        """Decide whether the incident should escalate, and to whom."""
        policy = self.policy_for(incident)
        if policy is None:
            return EscalationDecision(False, incident.tier, None, [])

        step = policy.step_for_elapsed(elapsed_minutes)
        if step is None:
            return EscalationDecision(False, incident.tier, None, [])

        should = step.tier.rank > incident.tier.rank
        engineer = self.on_call_for(step.tier)
        return EscalationDecision(
            should_escalate=should,
            target_tier=step.tier,
            engineer=engineer,
            channels=step.notify_channels,
        )
