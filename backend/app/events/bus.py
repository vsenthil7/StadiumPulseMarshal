"""Domain events and an async in-process event bus.

Services publish ``DomainEvent``s on meaningful state changes (incident created,
state changed, remediation decided, SLO breached). Subscribers (the webhook
dispatcher, metrics, future integrations) react asynchronously. The bus is
deliberately in-process and dependency-free; it can be swapped for a real broker
behind the same publish/subscribe interface.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.logging import get_logger

log = get_logger(__name__)


class EventType(str, Enum):
    INCIDENT_CREATED = "incident.created"
    INCIDENT_STATE_CHANGED = "incident.state_changed"
    INCIDENT_ESCALATED = "incident.escalated"
    INCIDENT_ASSIGNED = "incident.assigned"
    REMEDIATION_DECIDED = "remediation.decided"
    SLO_BREACHED = "slo.breached"


class DomainEvent(BaseModel):
    type: EventType
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    subject_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


Handler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """Async publish/subscribe bus with per-type and wildcard handlers."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = {}
        self._wildcard: list[Handler] = []

    def subscribe(self, event_type: EventType | None, handler: Handler) -> None:
        if event_type is None:
            self._wildcard.append(handler)
        else:
            self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: DomainEvent) -> int:
        """Dispatch an event to all matching handlers; returns handler count.

        Handlers are awaited concurrently; a failing handler is logged and does
        not prevent the others from running.
        """
        handlers = list(self._handlers.get(event.type, [])) + list(self._wildcard)
        if not handlers:
            return 0
        results = await asyncio.gather(
            *(self._safe(h, event) for h in handlers), return_exceptions=True
        )
        return len(results)

    async def _safe(self, handler: Handler, event: DomainEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("event handler failed for %s: %s", event.type.value, exc)
