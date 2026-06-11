"""Refresh-token persistence.

A small async repository abstraction for refresh tokens so the rotation logic in
``RefreshStore`` works against durable storage. Two implementations: in-memory
(demo / tests) and SQL (production). The interface is deliberately minimal —
add, fetch, mark-consumed, revoke-family, prune.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class RefreshRecord:
    token: str
    family_id: str
    subject: str
    expires_at: float
    consumed: bool = False
    revoked: bool = False

    @property
    def is_live(self) -> bool:
        return (
            not self.revoked
            and not self.consumed
            and self.expires_at >= time.time()
        )


class RefreshTokenRepository(Protocol):
    async def add(self, rec: RefreshRecord) -> None: ...
    async def get(self, token: str) -> RefreshRecord | None: ...
    async def mark_consumed(self, token: str) -> None: ...
    async def revoke_family(self, family_id: str) -> None: ...
    async def is_family_revoked(self, family_id: str) -> bool: ...
    async def prune(self, now: float | None = None) -> int: ...


class MemoryRefreshTokenRepository:
    def __init__(self) -> None:
        self._by_token: dict[str, RefreshRecord] = {}
        self._revoked: set[str] = set()

    async def add(self, rec: RefreshRecord) -> None:
        self._by_token[rec.token] = rec

    async def get(self, token: str) -> RefreshRecord | None:
        rec = self._by_token.get(token)
        if rec is None:
            return None
        if rec.family_id in self._revoked:
            rec.revoked = True
        return rec

    async def mark_consumed(self, token: str) -> None:
        rec = self._by_token.get(token)
        if rec is not None:
            rec.consumed = True

    async def revoke_family(self, family_id: str) -> None:
        self._revoked.add(family_id)
        for rec in self._by_token.values():
            if rec.family_id == family_id:
                rec.revoked = True

    async def is_family_revoked(self, family_id: str) -> bool:
        return family_id in self._revoked

    async def prune(self, now: float | None = None) -> int:
        now = now or time.time()
        dead = [
            t for t, r in self._by_token.items()
            if r.expires_at < now or r.consumed or r.revoked
        ]
        for t in dead:
            del self._by_token[t]
        return len(dead)


class SQLRefreshTokenRepository:
    def __init__(self, db) -> None:
        self._db = db

    async def add(self, rec: RefreshRecord) -> None:
        from app.repositories.sql.database import RefreshTokenRow

        async with self._db.session() as s:
            s.add(RefreshTokenRow(
                token=rec.token, family_id=rec.family_id, subject=rec.subject,
                expires_at=rec.expires_at, consumed=rec.consumed,
                revoked=rec.revoked,
            ))
            await s.commit()

    async def get(self, token: str) -> RefreshRecord | None:
        from app.repositories.sql.database import RefreshTokenRow

        async with self._db.session() as s:
            row = await s.get(RefreshTokenRow, token)
            if row is None:
                return None
            return RefreshRecord(
                token=row.token, family_id=row.family_id, subject=row.subject,
                expires_at=row.expires_at, consumed=row.consumed,
                revoked=row.revoked,
            )

    async def mark_consumed(self, token: str) -> None:
        from app.repositories.sql.database import RefreshTokenRow

        async with self._db.session() as s:
            row = await s.get(RefreshTokenRow, token)
            if row is not None:
                row.consumed = True
                await s.commit()

    async def revoke_family(self, family_id: str) -> None:
        from sqlalchemy import update

        from app.repositories.sql.database import RefreshTokenRow

        async with self._db.session() as s:
            await s.execute(
                update(RefreshTokenRow)
                .where(RefreshTokenRow.family_id == family_id)
                .values(revoked=True)
            )
            await s.commit()

    async def is_family_revoked(self, family_id: str) -> bool:
        from sqlalchemy import select

        from app.repositories.sql.database import RefreshTokenRow

        async with self._db.session() as s:
            row = (await s.execute(
                select(RefreshTokenRow.revoked)
                .where(RefreshTokenRow.family_id == family_id)
                .where(RefreshTokenRow.revoked.is_(True))
                .limit(1)
            )).first()
            return row is not None

    async def prune(self, now: float | None = None) -> int:
        from sqlalchemy import delete, or_

        from app.repositories.sql.database import RefreshTokenRow

        now = now or time.time()
        async with self._db.session() as s:
            result = await s.execute(
                delete(RefreshTokenRow).where(
                    or_(
                        RefreshTokenRow.expires_at < now,
                        RefreshTokenRow.consumed.is_(True),
                        RefreshTokenRow.revoked.is_(True),
                    )
                )
            )
            await s.commit()
            return result.rowcount or 0
