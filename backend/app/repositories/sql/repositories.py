"""SQLAlchemy-backed repository implementations.

Each repo serialises the Pydantic model to JSON for storage and rehydrates on
read, so behaviour matches the in-memory repos exactly.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.models.domain import ApprovalDecision, RemediationAction
from app.models.enums import RemediationStatus
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
from app.repositories.sql.database import (
    AuditRow,
    BudgetRow,
    Database,
    IncidentRow,
    NotificationRow,
    RemediationRow,
)


class SQLIncidentRepository(IncidentRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, incident: Incident) -> Incident:
        async with self._db.session() as s:
            s.add(
                IncidentRow(
                    id=incident.id,
                    venue_id=incident.venue_id,
                    is_open=incident.is_open,
                    created_at=incident.created_at.isoformat(),
                    document=incident.model_dump(mode="json"),
                )
            )
            await s.commit()
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        async with self._db.session() as s:
            row = await s.get(IncidentRow, incident_id)
            return Incident.model_validate(row.document) if row else None

    async def update(self, incident: Incident) -> Incident:
        async with self._db.session() as s:
            row = await s.get(IncidentRow, incident.id)
            if row is None:
                row = IncidentRow(id=incident.id)
                s.add(row)
            row.venue_id = incident.venue_id
            row.is_open = incident.is_open
            row.created_at = incident.created_at.isoformat()
            row.document = incident.model_dump(mode="json")
            await s.commit()
        return incident

    def _base_query(self, *, open_only: bool, venue_id: str | None):
        q = select(IncidentRow)
        if open_only:
            q = q.where(IncidentRow.is_open.is_(True))
        if venue_id is not None:
            q = q.where(IncidentRow.venue_id == venue_id)
        return q

    async def list(
        self,
        *,
        open_only: bool = False,
        venue_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Incident]:
        q = (
            self._base_query(open_only=open_only, venue_id=venue_id)
            .order_by(IncidentRow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        async with self._db.session() as s:
            rows = (await s.execute(q)).scalars().all()
            return [Incident.model_validate(r.document) for r in rows]

    async def count(
        self, *, open_only: bool = False, venue_id: str | None = None
    ) -> int:
        q = self._base_query(open_only=open_only, venue_id=venue_id)
        async with self._db.session() as s:
            count_q = select(func.count()).select_from(q.subquery())
            return int((await s.execute(count_q)).scalar_one())


class SQLRemediationRepository(RemediationRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add_many(self, actions: list[RemediationAction]) -> None:
        async with self._db.session() as s:
            for a in actions:
                existing = await s.get(RemediationRow, a.id)
                if existing is None:
                    s.add(
                        RemediationRow(
                            id=a.id,
                            status=a.status.value,
                            document=a.model_dump(mode="json"),
                        )
                    )
            await s.commit()

    async def get(self, action_id: str) -> RemediationAction | None:
        async with self._db.session() as s:
            row = await s.get(RemediationRow, action_id)
            return RemediationAction.model_validate(row.document) if row else None

    async def update(self, action: RemediationAction) -> RemediationAction:
        async with self._db.session() as s:
            row = await s.get(RemediationRow, action.id)
            if row is None:
                row = RemediationRow(id=action.id)
                s.add(row)
            row.status = action.status.value
            row.document = action.model_dump(mode="json")
            await s.commit()
        return action

    async def list(self, *, pending: bool = False) -> list[RemediationAction]:
        q = select(RemediationRow)
        if pending:
            q = q.where(
                RemediationRow.status.in_(
                    [
                        RemediationStatus.PROPOSED.value,
                        RemediationStatus.AWAITING_APPROVAL.value,
                    ]
                )
            )
        async with self._db.session() as s:
            rows = (await s.execute(q)).scalars().all()
            return [RemediationAction.model_validate(r.document) for r in rows]


class SQLAuditRepository(AuditRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, decision: ApprovalDecision) -> ApprovalDecision:
        async with self._db.session() as s:
            s.add(AuditRow(document=decision.model_dump(mode="json")))
            await s.commit()
        return decision

    async def list(self) -> list[ApprovalDecision]:
        async with self._db.session() as s:
            rows = (
                await s.execute(select(AuditRow).order_by(AuditRow.seq))
            ).scalars().all()
            return [ApprovalDecision.model_validate(r.document) for r in rows]


class SQLNotificationRepository(NotificationRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, notification: Notification) -> Notification:
        async with self._db.session() as s:
            s.add(
                NotificationRow(
                    id=notification.id,
                    incident_id=notification.incident_id,
                    created_at=notification.created_at.isoformat(),
                    document=notification.model_dump(mode="json"),
                )
            )
            await s.commit()
        return notification

    async def update(self, notification: Notification) -> Notification:
        async with self._db.session() as s:
            row = await s.get(NotificationRow, notification.id)
            if row is None:
                row = NotificationRow(
                    id=notification.id,
                    incident_id=notification.incident_id,
                    created_at=notification.created_at.isoformat(),
                )
                s.add(row)
            row.document = notification.model_dump(mode="json")
            await s.commit()
        return notification

    async def list(
        self, *, incident_id: str | None = None
    ) -> list[Notification]:
        q = select(NotificationRow).order_by(NotificationRow.created_at)
        if incident_id is not None:
            q = q.where(NotificationRow.incident_id == incident_id)
        async with self._db.session() as s:
            rows = (await s.execute(q)).scalars().all()
            return [Notification.model_validate(r.document) for r in rows]


class SQLSLORepository(SLORepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save_budget(self, budget: ErrorBudget) -> ErrorBudget:
        async with self._db.session() as s:
            row = await s.get(BudgetRow, budget.slo_id)
            if row is None:
                row = BudgetRow(slo_id=budget.slo_id)
                s.add(row)
            row.document = budget.model_dump(mode="json")
            await s.commit()
        return budget

    async def list_budgets(self) -> list[ErrorBudget]:
        async with self._db.session() as s:
            rows = (await s.execute(select(BudgetRow))).scalars().all()
            return [ErrorBudget.model_validate(r.document) for r in rows]
