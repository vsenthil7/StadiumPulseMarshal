"""Webhook subscription model and delivery record."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.events.bus import EventType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_webhook_id() -> str:
    return f"WH-{uuid.uuid4().hex[:8]}"


class WebhookSubscription(BaseModel):
    """A registered webhook endpoint subscribed to event types."""

    id: str = Field(default_factory=new_webhook_id)
    url: str
    event_types: list[EventType] = Field(default_factory=list)
    active: bool = True
    description: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    last_status: int | None = None
    last_delivery_at: datetime | None = None
    failure_count: int = 0

    def wants(self, event_type: EventType) -> bool:
        return self.active and (
            not self.event_types or event_type in self.event_types
        )
