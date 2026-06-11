"""Webhook repository and event-driven delivery service.

The repository stores subscriptions; the dispatcher subscribes to the event bus
and POSTs matching events to active webhook URLs. Delivery uses an injected
async HTTP client so tests can supply a mock transport. Delivery failures are
recorded on the subscription (status, failure count) but never raise.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.logging import get_logger
from app.events.bus import DomainEvent, EventBus
from app.models.webhook import WebhookSubscription
from app.observability.metrics import get_metrics

log = get_logger(__name__)


class WebhookRepository:
    def __init__(self) -> None:
        self._items: dict[str, WebhookSubscription] = {}

    def add(self, sub: WebhookSubscription) -> WebhookSubscription:
        self._items[sub.id] = sub
        return sub

    def get(self, webhook_id: str) -> WebhookSubscription | None:
        return self._items.get(webhook_id)

    def list(self) -> list[WebhookSubscription]:
        return list(self._items.values())

    def delete(self, webhook_id: str) -> bool:
        return self._items.pop(webhook_id, None) is not None


class WebhookDispatcher:
    """Delivers domain events to subscribed webhooks."""

    def __init__(
        self,
        repo: WebhookRepository,
        http: httpx.AsyncClient,
        *,
        timeout: float = 5.0,
    ) -> None:
        self._repo = repo
        self._http = http
        self._timeout = timeout

    def register(self, bus: EventBus) -> None:
        bus.subscribe(None, self.on_event)

    async def on_event(self, event: DomainEvent) -> None:
        for sub in self._repo.list():
            if not sub.wants(event.type):
                continue
            await self._deliver(sub, event)

    async def _deliver(
        self, sub: WebhookSubscription, event: DomainEvent
    ) -> None:
        metrics = get_metrics()
        try:
            resp = await self._http.post(
                sub.url,
                json={
                    "type": event.type.value,
                    "at": event.at.isoformat(),
                    "subject_id": event.subject_id,
                    "payload": event.payload,
                },
                timeout=self._timeout,
            )
            sub.last_status = resp.status_code
            sub.last_delivery_at = datetime.now(timezone.utc)
            if resp.status_code >= 400:
                sub.failure_count += 1
                metrics.webhook_deliveries.inc(result="error")
            else:
                metrics.webhook_deliveries.inc(result="ok")
        except Exception as exc:  # network error etc.
            sub.failure_count += 1
            sub.last_status = None
            sub.last_delivery_at = datetime.now(timezone.utc)
            metrics.webhook_deliveries.inc(result="exception")
            log.warning("webhook %s delivery failed: %s", sub.id, exc)
