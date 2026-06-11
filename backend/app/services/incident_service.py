"""Incident service: orchestrates the operational response.

Owns incident creation from problems, lifecycle transitions (validated against
the state machine), assignment, escalation (via the escalation engine +
notifications), and linking remediation decisions onto the incident timeline.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.models.domain import Problem
from app.models.incident import (
    EscalationTier,
    Incident,
    IncidentEvent,
    IncidentEventType,
    IncidentState,
    can_transition,
)
from app.models.notification import NotificationChannel
from app.repositories.base import IncidentRepository
from app.services.escalation_engine import EscalationEngine
from app.services.notification_service import NotificationService

log = get_logger(__name__)


class IncidentError(Exception):
    """Raised on invalid incident operations (e.g. illegal transition)."""


def _new_id() -> str:
    return f"INC-{uuid.uuid4().hex[:8]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IncidentService:
    def __init__(
        self,
        repo: IncidentRepository,
        escalation: EscalationEngine,
        notifications: NotificationService,
        events=None,
    ) -> None:
        self._repo = repo
        self._escalation = escalation
        self._notifications = notifications
        self._events = events

    async def _emit(self, event_type, subject_id: str, **payload) -> None:
        if self._events is None:
            return
        from app.events.bus import DomainEvent

        await self._events.publish(
            DomainEvent(type=event_type, subject_id=subject_id, payload=payload)
        )

    # --- creation ----------------------------------------------------------
    async def create_from_problem(
        self, problem: Problem, *, venue_id: str | None = None,
        match_id: str | None = None,
    ) -> Incident:
        incident = Incident(
            id=_new_id(),
            problem_id=problem.id,
            title=problem.title,
            severity=problem.severity,
            venue_id=venue_id,
            match_id=match_id,
            impact_summary=problem.impact_summary,
        )
        incident.add_event(
            IncidentEvent(
                type=IncidentEventType.CREATED,
                detail=f"Incident opened from problem {problem.id}",
            )
        )
        await self._repo.add(incident)
        from app.events.bus import EventType
        from app.observability.metrics import get_metrics

        get_metrics().incidents_created.inc(severity=problem.severity.value)
        await self._emit(
            EventType.INCIDENT_CREATED, incident.id,
            title=incident.title, severity=incident.severity.value,
        )
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        return await self._repo.get(incident_id)

    async def list(
        self, *, open_only: bool = False, venue_id: str | None = None,
        offset: int = 0, limit: int = 50,
    ) -> list[Incident]:
        return await self._repo.list(
            open_only=open_only, venue_id=venue_id, offset=offset, limit=limit
        )

    async def count(
        self, *, open_only: bool = False, venue_id: str | None = None
    ) -> int:
        return await self._repo.count(open_only=open_only, venue_id=venue_id)

    # --- lifecycle ---------------------------------------------------------
    async def transition(
        self, incident_id: str, target: IncidentState, *, actor: str = "system",
        note: str = "",
    ) -> Incident:
        incident = await self._require(incident_id)
        if not can_transition(incident.state, target):
            raise IncidentError(
                f"Illegal transition {incident.state.value} -> {target.value}"
            )
        prev = incident.state
        incident.state = target
        if target == IncidentState.ACKNOWLEDGED and incident.acknowledged_at is None:
            incident.acknowledged_at = _now()
        if target == IncidentState.RESOLVED and incident.resolved_at is None:
            incident.resolved_at = _now()
        incident.add_event(
            IncidentEvent(
                type=IncidentEventType.STATE_CHANGE,
                actor=actor,
                detail=f"{prev.value} -> {target.value}. {note}".strip(),
                data={"from": prev.value, "to": target.value},
            )
        )
        await self._repo.update(incident)
        from app.events.bus import EventType

        await self._emit(
            EventType.INCIDENT_STATE_CHANGED, incident.id,
            **{"from": prev.value, "to": target.value},
        )
        return incident

    async def assign(
        self, incident_id: str, assignee: str, *, actor: str = "system"
    ) -> Incident:
        incident = await self._require(incident_id)
        incident.assignee = assignee
        incident.add_event(
            IncidentEvent(
                type=IncidentEventType.ASSIGNED,
                actor=actor,
                detail=f"Assigned to {assignee}",
            )
        )
        await self._repo.update(incident)
        return incident

    async def add_note(
        self, incident_id: str, note: str, *, actor: str = "system"
    ) -> Incident:
        incident = await self._require(incident_id)
        incident.add_event(
            IncidentEvent(type=IncidentEventType.NOTE, actor=actor, detail=note)
        )
        await self._repo.update(incident)
        return incident

    async def link_remediation(
        self, incident_id: str, remediation_id: str,
        event_type: IncidentEventType, *, actor: str = "system", detail: str = "",
    ) -> Incident:
        incident = await self._require(incident_id)
        if remediation_id not in incident.remediation_ids:
            incident.remediation_ids.append(remediation_id)
        incident.add_event(
            IncidentEvent(type=event_type, actor=actor, detail=detail,
                          data={"remediation_id": remediation_id})
        )
        await self._repo.update(incident)
        return incident

    # --- escalation --------------------------------------------------------
    async def evaluate_escalation(self, incident_id: str) -> Incident:
        """Apply the escalation policy based on incident age; page on-call."""
        incident = await self._require(incident_id)
        elapsed = (_now() - incident.created_at).total_seconds() / 60.0
        decision = self._escalation.evaluate(incident, elapsed)
        if decision.should_escalate:
            incident.tier = decision.target_tier
            incident.add_event(
                IncidentEvent(
                    type=IncidentEventType.ESCALATED,
                    detail=f"Escalated to {decision.target_tier.value}"
                    + (f" ({decision.engineer.name})" if decision.engineer else ""),
                    data={"tier": decision.target_tier.value},
                )
            )
            await self._repo.update(incident)
            if decision.engineer:
                for ch in decision.channels or decision.engineer.channels:
                    await self._notifications.notify(
                        incident,
                        channel=NotificationChannel(ch)
                        if ch in NotificationChannel._value2member_map_
                        else NotificationChannel.EMAIL,
                        recipient=decision.engineer.handle
                        or decision.engineer.name,
                        subject=f"[{incident.severity.value}] {incident.title}",
                        body=(
                            f"Incident {incident.id} escalated to "
                            f"{decision.target_tier.value}. Please respond."
                        ),
                    )
                    incident.add_event(
                        IncidentEvent(
                            type=IncidentEventType.NOTIFICATION_SENT,
                            detail=f"Paged {decision.engineer.name} via {ch}",
                        )
                    )
                await self._repo.update(incident)
        return incident

    async def _require(self, incident_id: str) -> Incident:
        incident = await self._repo.get(incident_id)
        if incident is None:
            raise IncidentError(f"Incident {incident_id} not found")
        return incident

    # --- search & bulk -----------------------------------------------------
    async def search(
        self,
        *,
        state=None,
        severity=None,
        text: str | None = None,
        venue_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ):
        """Filter incidents by state, severity, free text and venue."""
        all_incidents = await self._repo.list(
            venue_id=venue_id, offset=0, limit=10_000
        )
        results = []
        needle = (text or "").lower()
        for inc in all_incidents:
            if state is not None and inc.state != state:
                continue
            if severity is not None and inc.severity != severity:
                continue
            if needle and needle not in (
                inc.title.lower() + " " + inc.impact_summary.lower()
            ):
                continue
            results.append(inc)
        total = len(results)
        return results[offset : offset + limit], total

    async def bulk_transition(
        self, incident_ids: list[str], target, *, actor: str = "system"
    ) -> dict:
        """Transition many incidents; report per-id success/failure."""
        succeeded: list[str] = []
        failed: dict[str, str] = {}
        for iid in incident_ids:
            try:
                await self.transition(iid, target, actor=actor)
                succeeded.append(iid)
            except IncidentError as exc:
                failed[iid] = str(exc)
        return {"succeeded": succeeded, "failed": failed}
