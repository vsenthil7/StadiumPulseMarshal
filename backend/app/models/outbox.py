"""Transactional outbox model.

The outbox pattern guarantees that a domain event is persisted atomically with
the state change that produced it. A separate relay later reads pending entries
and publishes them to the event bus, marking them dispatched. This removes the
"dual-write" race where an in-process event is lost if the process dies after
the DB commit but before delivery.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.events.bus import DomainEvent, EventType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_outbox_id() -> str:
    return f"OBX-{uuid.uuid4().hex[:12]}"


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    FAILED = "FAILED"


class OutboxEntry(BaseModel):
    """A durably-stored domain event awaiting relay to the bus."""

    id: str = Field(default_factory=new_outbox_id)
    event_type: EventType
    subject_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    status: OutboxStatus = OutboxStatus.PENDING
    created_at: datetime = Field(default_factory=_utcnow)
    dispatched_at: datetime | None = None
    attempts: int = 0
    last_error: str = ""

    def to_event(self) -> DomainEvent:
        return DomainEvent(
            type=self.event_type,
            at=self.created_at,
            subject_id=self.subject_id,
            payload=self.payload,
        )

    @classmethod
    def from_event(cls, event: DomainEvent) -> "OutboxEntry":
        return cls(
            event_type=event.type,
            subject_id=event.subject_id,
            payload=event.payload,
        )
