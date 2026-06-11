"""Refresh-token rotation with theft detection.

Implements the OAuth2 refresh-token rotation pattern:
- each login starts a token *family*;
- every refresh consumes the presented refresh token and issues a new one in the
  same family (rotation);
- presenting an already-rotated (consumed) token is treated as **reuse** — a
  signal the token was stolen — and the whole family is revoked;
- logout revokes the active family.

This is an in-memory store (suits the demo / single-process deployment). The
interface is intentionally small so a Redis/SQL implementation can be dropped in
without touching callers.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field


@dataclass
class _TokenRecord:
    token: str
    family_id: str
    subject: str
    expires_at: float
    consumed: bool = False


@dataclass
class RefreshStore:
    ttl_seconds: int = 30 * 24 * 3600  # 30 days
    _by_token: dict[str, _TokenRecord] = field(default_factory=dict)
    _revoked_families: set[str] = field(default_factory=set)

    # --- issuance ------------------------------------------------------------
    def issue(self, subject: str, family_id: str | None = None) -> tuple[str, str]:
        """Issue a refresh token. Starts a new family unless one is given."""
        fam = family_id or secrets.token_urlsafe(12)
        token = secrets.token_urlsafe(32)
        self._by_token[token] = _TokenRecord(
            token=token, family_id=fam, subject=subject,
            expires_at=time.time() + self.ttl_seconds,
        )
        return token, fam

    # --- rotation ------------------------------------------------------------
    def rotate(self, presented: str) -> tuple[str, str] | None:
        """Validate + consume a refresh token and issue its successor.

        Returns ``(new_token, family_id)`` on success. Returns ``None`` if the
        token is unknown/expired. On **reuse** (a consumed token presented
        again) the family is revoked and ``ReuseError`` is raised.
        """
        rec = self._by_token.get(presented)
        if rec is None:
            return None
        if rec.family_id in self._revoked_families:
            return None
        if rec.expires_at < time.time():
            return None
        if rec.consumed:
            # Token reuse → likely theft. Burn the whole family.
            self.revoke_family(rec.family_id)
            raise ReuseError(rec.family_id)
        rec.consumed = True
        return self.issue(rec.subject, family_id=rec.family_id)

    def subject_for(self, presented: str) -> str | None:
        rec = self._by_token.get(presented)
        if rec is None or rec.family_id in self._revoked_families:
            return None
        if rec.expires_at < time.time() or rec.consumed:
            return None
        return rec.subject

    # --- revocation ----------------------------------------------------------
    def revoke_family(self, family_id: str) -> None:
        self._revoked_families.add(family_id)

    def revoke_token(self, presented: str) -> None:
        rec = self._by_token.get(presented)
        if rec is not None:
            self.revoke_family(rec.family_id)

    def is_family_revoked(self, family_id: str) -> bool:
        return family_id in self._revoked_families


class ReuseError(RuntimeError):
    """Raised when a rotated (consumed) refresh token is presented again."""

    def __init__(self, family_id: str) -> None:
        super().__init__(f"Refresh token reuse detected for family {family_id}")
        self.family_id = family_id
