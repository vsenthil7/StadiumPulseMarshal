"""Repository interfaces.

Define the persistence contract independently of any storage backend. The
in-memory and SQL implementations both satisfy these, selected by the factory,
so services never depend on a concrete store.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.domain import ApprovalDecision, RemediationAction
from app.models.incident import Incident
from app.models.notification import Notification
from app.models.slo import ErrorBudget


class IncidentRepository(ABC):
    @abstractmethod
    async def add(self, incident: Incident) -> Incident: ...

    @abstractmethod
    async def get(self, incident_id: str) -> Incident | None: ...

    @abstractmethod
    async def update(self, incident: Incident) -> Incident: ...

    @abstractmethod
    async def list(
        self,
        *,
        open_only: bool = False,
        venue_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Incident]: ...

    @abstractmethod
    async def count(
        self, *, open_only: bool = False, venue_id: str | None = None
    ) -> int: ...


class RemediationRepository(ABC):
    @abstractmethod
    async def add_many(self, actions: list[RemediationAction]) -> None: ...

    @abstractmethod
    async def get(self, action_id: str) -> RemediationAction | None: ...

    @abstractmethod
    async def update(self, action: RemediationAction) -> RemediationAction: ...

    @abstractmethod
    async def list(self, *, pending: bool = False) -> list[RemediationAction]: ...


class AuditRepository(ABC):
    @abstractmethod
    async def add(self, decision: ApprovalDecision) -> ApprovalDecision: ...

    @abstractmethod
    async def list(self) -> list[ApprovalDecision]: ...


class NotificationRepository(ABC):
    @abstractmethod
    async def add(self, notification: Notification) -> Notification: ...

    @abstractmethod
    async def update(self, notification: Notification) -> Notification: ...

    @abstractmethod
    async def list(
        self, *, incident_id: str | None = None
    ) -> list[Notification]: ...


class SLORepository(ABC):
    @abstractmethod
    async def save_budget(self, budget: ErrorBudget) -> ErrorBudget: ...

    @abstractmethod
    async def list_budgets(self) -> list[ErrorBudget]: ...


class OutboxRepository(ABC):
    @abstractmethod
    async def add(self, entry) -> object: ...

    @abstractmethod
    async def list_pending(self, *, limit: int = 100) -> list: ...

    @abstractmethod
    async def mark_dispatched(self, entry_id: str) -> None: ...

    @abstractmethod
    async def mark_failed(self, entry_id: str, error: str) -> None: ...

    @abstractmethod
    async def list_all(self) -> list: ...


class AuditLogRepository(ABC):
    @abstractmethod
    async def add(self, entry) -> object: ...

    @abstractmethod
    async def query(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        after_cursor: str | None = None,
        limit: int = 50,
    ) -> list: ...

    @abstractmethod
    async def count(self) -> int: ...
