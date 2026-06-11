"""Durable persistence backends for the P6 width modules.

Each store mirrors the in-memory service's dict[id → pydantic model] but reads
through to a SQL table (thin JSON document rows). Services accept one of these
as an optional ``persistence`` dependency; when absent they stay purely
in-memory (the default for mock/demo and tests without a DATABASE_URL).

These backends are intentionally simple: load-all on startup into the service's
cache, write-through on mutations. For the matchday console's data volumes this
is more than sufficient and keeps the services' query logic unchanged.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from app.repositories.sql.database import (
    ChangeEventRow,
    DavisFeedbackRow,
    Database,
    PostmortemRow,
    RunbookExecutionRow,
    RunbookRow,
)


class RunbookSqlStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self) -> dict[str, dict]:
        async with self._db.session() as s:
            rows = (await s.execute(select(RunbookRow))).scalars().all()
            return {r.id: r.document for r in rows}

    async def save(self, rb_id: str, category: str, document: dict) -> None:
        async with self._db.session() as s:
            await s.merge(RunbookRow(id=rb_id, category=category, document=document))
            await s.commit()

    async def delete(self, rb_id: str) -> None:
        async with self._db.session() as s:
            await s.execute(delete(RunbookRow).where(RunbookRow.id == rb_id))
            await s.commit()

    async def save_execution(self, ex_id: str, runbook_id: str,
                             started_at: str, document: dict) -> None:
        async with self._db.session() as s:
            await s.merge(RunbookExecutionRow(
                id=ex_id, runbook_id=runbook_id, started_at=started_at,
                document=document))
            await s.commit()

    async def load_executions(self) -> list[dict]:
        async with self._db.session() as s:
            rows = (await s.execute(select(RunbookExecutionRow))).scalars().all()
            return [r.document for r in rows]


class PostmortemSqlStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self) -> dict[str, dict]:
        async with self._db.session() as s:
            rows = (await s.execute(select(PostmortemRow))).scalars().all()
            return {r.id: r.document for r in rows}

    async def save(self, pm_id: str, status: str, incident_id: str | None,
                   created_at: str, document: dict) -> None:
        async with self._db.session() as s:
            await s.merge(PostmortemRow(
                id=pm_id, status=status, incident_id=incident_id,
                created_at=created_at, document=document))
            await s.commit()


class ChangeEventSqlStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self) -> dict[str, dict]:
        async with self._db.session() as s:
            rows = (await s.execute(select(ChangeEventRow))).scalars().all()
            return {r.id: r.document for r in rows}

    async def save(self, ev_id: str, service_id: str, change_type: str,
                   at: str, document: dict) -> None:
        async with self._db.session() as s:
            await s.merge(ChangeEventRow(
                id=ev_id, service_id=service_id, change_type=change_type,
                at=at, document=document))
            await s.commit()


class DavisFeedbackSqlStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self) -> dict[str, dict]:
        async with self._db.session() as s:
            rows = (await s.execute(select(DavisFeedbackRow))).scalars().all()
            return {r.problem_id: r.document for r in rows}

    async def save(self, problem_id: str, rank: float, document: dict) -> None:
        async with self._db.session() as s:
            await s.merge(DavisFeedbackRow(
                problem_id=problem_id, rank=rank, document=document))
            await s.commit()
