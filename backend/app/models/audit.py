"""First-class audit log entry.

Distinct from the remediation ApprovalDecision audit: this records *every*
mutation across the system (actor, action, resource, before/after snapshot) as a
queryable, cursor-pageable entity. The id is time-ordered (sortable) so it
doubles as a stable pagination cursor.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_audit_id() -> str:
    # Time-prefixed id: lexicographically sortable by creation time, so it can
    # serve as a stable opaque pagination cursor.
    return f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:8]}"


class AuditEntry(BaseModel):
    id: str = Field(default_factory=new_audit_id)
    actor: str
    action: str
    resource_type: str
    resource_id: str
    at: datetime = Field(default_factory=_utcnow)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
