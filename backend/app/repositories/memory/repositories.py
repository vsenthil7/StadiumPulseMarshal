"""In-memory repository implementations.

Thread-unsafe but adequate for single-process demo/dev; mirror the SQL repos'
behaviour exactly so the same contract tests pass against both.
"""
from __future__ import annotations

from app.models.domain import ApprovalDecision, RemediationAction
from app.models.incident import Incident
from app.models.notification import Notification
from app.models.slo import ErrorBudget
from app.repositories.base import (
    AuditRepository,
    IncidentRepository,
    NotificationRepository,
    RemediationRepository,
    SLORepository,
)


class MemoryIncidentRepository(IncidentRepository):
    def __init__(self) -> None:
        self._items: dict[str, Incident] = {}

    async def add(self, incident: Incident) -> Incident:
        self._items[incident.id] = incident
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        return self._items.get(incident_id)

    async def update(self, incident: Incident) -> Incident:
        self._items[incident.id] = incident
        return incident

    def _filtered(self, *, open_only: bool, venue_id: str | None) -> list[Incident]:
        items = list(self._items.values())
        if open_only:
            items = [i for i in items if i.is_open]
        if venue_id is not None:
            items = [i for i in items if i.venue_id == venue_id]
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items

    async def list(
        self,
        *,
        open_only: bool = False,
        venue_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Incident]:
        items = self._filtered(open_only=open_only, venue_id=venue_id)
        return items[offset : offset + limit]

    async def count(
        self, *, open_only: bool = False, venue_id: str | None = None
    ) -> int:
        return len(self._filtered(open_only=open_only, venue_id=venue_id))


class MemoryRemediationRepository(RemediationRepository):
    def __init__(self) -> None:
        self._items: dict[str, RemediationAction] = {}

    async def add_many(self, actions: list[RemediationAction]) -> None:
        for a in actions:
            self._items.setdefault(a.id, a)

    async def get(self, action_id: str) -> RemediationAction | None:
        return self._items.get(action_id)

    async def update(self, action: RemediationAction) -> RemediationAction:
        self._items[action.id] = action
        return action

    async def list(self, *, pending: bool = False) -> list[RemediationAction]:
        from app.models.enums import RemediationStatus

        items = list(self._items.values())
        if pending:
            items = [
                a
                for a in items
                if a.status
                in (
                    RemediationStatus.PROPOSED,
                    RemediationStatus.AWAITING_APPROVAL,
                )
            ]
        return items


class MemoryAuditRepository(AuditRepository):
    def __init__(self) -> None:
        self._items: list[ApprovalDecision] = []

    async def add(self, decision: ApprovalDecision) -> ApprovalDecision:
        self._items.append(decision)
        return decision

    async def list(self) -> list[ApprovalDecision]:
        return list(self._items)


class MemoryNotificationRepository(NotificationRepository):
    def __init__(self) -> None:
        self._items: dict[str, Notification] = {}

    async def add(self, notification: Notification) -> Notification:
        self._items[notification.id] = notification
        return notification

    async def update(self, notification: Notification) -> Notification:
        self._items[notification.id] = notification
        return notification

    async def list(
        self, *, incident_id: str | None = None
    ) -> list[Notification]:
        items = list(self._items.values())
        if incident_id is not None:
            items = [n for n in items if n.incident_id == incident_id]
        items.sort(key=lambda n: n.created_at)
        return items


class MemorySLORepository(SLORepository):
    def __init__(self) -> None:
        self._budgets: dict[str, ErrorBudget] = {}

    async def save_budget(self, budget: ErrorBudget) -> ErrorBudget:
        self._budgets[budget.slo_id] = budget
        return budget

    async def list_budgets(self) -> list[ErrorBudget]:
        return list(self._budgets.values())


class MemoryOutboxRepository:
    """In-memory outbox (relay still provides at-least-once within a run)."""

    def __init__(self) -> None:
        self._items: dict[str, object] = {}

    async def add(self, entry):
        self._items[entry.id] = entry
        return entry

    async def list_pending(self, *, limit: int = 100):
        from app.models.outbox import OutboxStatus

        pending = [
            e for e in self._items.values()
            if e.status == OutboxStatus.PENDING  # type: ignore[attr-defined]
        ]
        pending.sort(key=lambda e: e.created_at)  # type: ignore[attr-defined]
        return pending[:limit]

    async def mark_dispatched(self, entry_id: str) -> None:
        from datetime import datetime, timezone

        from app.models.outbox import OutboxStatus

        e = self._items.get(entry_id)
        if e is not None:
            e.status = OutboxStatus.DISPATCHED  # type: ignore[attr-defined]
            e.dispatched_at = datetime.now(timezone.utc)  # type: ignore[attr-defined]

    async def mark_failed(self, entry_id: str, error: str) -> None:
        from app.models.outbox import OutboxStatus

        e = self._items.get(entry_id)
        if e is not None:
            e.attempts += 1  # type: ignore[attr-defined]
            e.last_error = error  # type: ignore[attr-defined]
            e.status = OutboxStatus.FAILED  # type: ignore[attr-defined]

    async def list_all(self):
        return list(self._items.values())


class MemoryAuditLogRepository:
    def __init__(self) -> None:
        self._items: list = []

    async def add(self, entry):
        self._items.append(entry)
        return entry

    async def query(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        after_cursor: str | None = None,
        limit: int = 50,
    ):
        items = sorted(self._items, key=lambda e: e.id)
        out = []
        for e in items:
            if after_cursor is not None and e.id <= after_cursor:
                continue
            if resource_type is not None and e.resource_type != resource_type:
                continue
            if resource_id is not None and e.resource_id != resource_id:
                continue
            if actor is not None and e.actor != actor:
                continue
            if action is not None and e.action != action:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

    async def count(self) -> int:
        return len(self._items)
