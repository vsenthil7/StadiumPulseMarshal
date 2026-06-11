"""Repository bundle and factory.

Groups the five repositories and builds either the in-memory or SQL-backed set
based on settings. Services depend only on this bundle.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.repositories.base import (
    AuditRepository,
    IncidentRepository,
    NotificationRepository,
    RemediationRepository,
    SLORepository,
)
from app.repositories.memory.repositories import (
    MemoryAuditRepository,
    MemoryIncidentRepository,
    MemoryNotificationRepository,
    MemoryRemediationRepository,
    MemorySLORepository,
)

log = get_logger(__name__)


@dataclass
class RepositoryBundle:
    incidents: IncidentRepository
    remediations: RemediationRepository
    audit: AuditRepository
    notifications: NotificationRepository
    slo: SLORepository
    outbox: object = None
    audit_log: object = None
    # Optional SQL database handle (for lifecycle management).
    database: object | None = None

    async def init(self) -> None:
        if self.database is not None:
            await self.database.create_all()  # type: ignore[attr-defined]

    async def dispose(self) -> None:
        if self.database is not None:
            await self.database.dispose()  # type: ignore[attr-defined]


def build_repositories(settings: Settings) -> RepositoryBundle:
    """Return a SQL-backed bundle when a DB URL is set, else in-memory."""
    if settings.database_url:
        from app.repositories.sql.database import Database
        from app.repositories.sql.repositories import (
            SQLAuditLogRepository,
            SQLAuditRepository,
            SQLIncidentRepository,
            SQLNotificationRepository,
            SQLOutboxRepository,
            SQLRemediationRepository,
            SQLSLORepository,
        )

        db = Database(settings.database_url)
        log.info("Using SQL persistence: %s", settings.database_url)
        return RepositoryBundle(
            incidents=SQLIncidentRepository(db),
            remediations=SQLRemediationRepository(db),
            audit=SQLAuditRepository(db),
            notifications=SQLNotificationRepository(db),
            slo=SQLSLORepository(db),
            outbox=SQLOutboxRepository(db),
            audit_log=SQLAuditLogRepository(db),
            database=db,
        )

    log.info("Using in-memory persistence")
    from app.repositories.memory.repositories import (
        MemoryAuditLogRepository,
        MemoryOutboxRepository,
    )

    return RepositoryBundle(
        incidents=MemoryIncidentRepository(),
        remediations=MemoryRemediationRepository(),
        audit=MemoryAuditRepository(),
        notifications=MemoryNotificationRepository(),
        slo=MemorySLORepository(),
        outbox=MemoryOutboxRepository(),
        audit_log=MemoryAuditLogRepository(),
    )
