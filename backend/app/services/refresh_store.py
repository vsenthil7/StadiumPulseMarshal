"""Refresh-token rotation with theft detection — repository-backed.

Implements the OAuth2 refresh-token rotation pattern over a pluggable
``RefreshTokenRepository`` (in-memory for the demo, SQL for production):
- each login starts a token *family*;
- every refresh consumes the presented token and issues a successor in the same
  family (rotation);
- presenting an already-rotated (consumed) token is **reuse** — a theft signal —
  and the whole family is revoked;
- logout revokes the active family;
- expired/consumed/revoked rows are pruned by ``prune()``.
"""
from __future__ import annotations

import secrets
import time

from app.repositories.refresh_tokens import (
    MemoryRefreshTokenRepository,
    RefreshRecord,
    RefreshTokenRepository,
)


class ReuseError(RuntimeError):
    """Raised when a rotated (consumed) refresh token is presented again."""

    def __init__(self, family_id: str) -> None:
        super().__init__(f"Refresh token reuse detected for family {family_id}")
        self.family_id = family_id


class RefreshStore:
    def __init__(
        self,
        repo: RefreshTokenRepository | None = None,
        ttl_seconds: int = 30 * 24 * 3600,
    ) -> None:
        self._repo: RefreshTokenRepository = repo or MemoryRefreshTokenRepository()
        self.ttl_seconds = ttl_seconds

    async def issue(self, subject: str, family_id: str | None = None) -> tuple[str, str]:
        """Issue a refresh token. Starts a new family unless one is given."""
        fam = family_id or secrets.token_urlsafe(12)
        token = secrets.token_urlsafe(32)
        await self._repo.add(RefreshRecord(
            token=token, family_id=fam, subject=subject,
            expires_at=time.time() + self.ttl_seconds,
        ))
        return token, fam

    async def rotate(self, presented: str) -> tuple[str, str] | None:
        """Validate + consume a token and issue its successor.

        Returns ``(new_token, family_id)``; ``None`` if unknown/expired/revoked.
        On reuse (a consumed token presented again) revokes the family and
        raises ``ReuseError``.
        """
        rec = await self._repo.get(presented)
        if rec is None:
            return None
        if rec.revoked or await self._repo.is_family_revoked(rec.family_id):
            return None
        if rec.expires_at < time.time():
            return None
        if rec.consumed:
            await self._repo.revoke_family(rec.family_id)
            raise ReuseError(rec.family_id)
        await self._repo.mark_consumed(presented)
        return await self.issue(rec.subject, family_id=rec.family_id)

    async def subject_for(self, presented: str) -> str | None:
        rec = await self._repo.get(presented)
        if rec is None or not rec.is_live:
            return None
        if await self._repo.is_family_revoked(rec.family_id):
            return None
        return rec.subject

    async def revoke_family(self, family_id: str) -> None:
        await self._repo.revoke_family(family_id)

    async def revoke_token(self, presented: str) -> None:
        rec = await self._repo.get(presented)
        if rec is not None:
            await self._repo.revoke_family(rec.family_id)

    async def is_family_revoked(self, family_id: str) -> bool:
        return await self._repo.is_family_revoked(family_id)

    async def prune(self) -> int:
        return await self._repo.prune()
