"""Audit service: records every mutation as a queryable audit entry."""
from __future__ import annotations

from typing import Any

from app.models.audit import AuditEntry


class AuditService:
    def __init__(self, repo) -> None:
        self._repo = repo

    async def record(
        self,
        *,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            actor=actor, action=action, resource_type=resource_type,
            resource_id=resource_id, before=before, after=after,
            metadata=metadata or {},
        )
        await self._repo.add(entry)
        return entry

    async def query(self, **kwargs) -> list[AuditEntry]:
        return await self._repo.query(**kwargs)

    async def count(self) -> int:
        return await self._repo.count()
