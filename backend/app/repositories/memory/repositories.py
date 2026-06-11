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
