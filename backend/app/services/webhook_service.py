"""Webhook repository and event-driven delivery with retry + dead-letter.

Delivery is attempted with bounded exponential backoff. After ``max_attempts``
consecutive failures the subscription is dead-lettered (no longer matched until
redriven). Each attempt is appended to the subscription's delivery log. Delivery
never raises into the caller; the event bus stays healthy regardless.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from app.core.logging import get_logger
from app.events.bus import DomainEvent, EventBus
from app.models.webhook import DeliveryAttempt, WebhookSubscription
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

    def list_dead_lettered(self) -> list[WebhookSubscription]:
        return [s for s in self._items.values() if s.dead_lettered]

    def delete(self, webhook_id: str) -> bool:
        return self._items.pop(webhook_id, None) is not None


class WebhookDispatcher:
    """Delivers domain events to subscribed webhooks with retry + dead-letter."""

    def __init__(
        self,
        repo: WebhookRepository,
        http: httpx.AsyncClient,
        *,
        timeout: float = 5.0,
        max_attempts: int = 3,
        base_backoff: float = 0.01,
    ) -> None:
        self._repo = repo
        self._http = http
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._base_backoff = base_backoff

    def register(self, bus: EventBus) -> None:
        bus.subscribe(None, self.on_event)

    async def post_message(self, url: str, payload: dict) -> bool:
        """One-shot POST to a specific URL with the same retry/backoff policy.

        Used for out-of-band messages (e.g. the burn digest) that aren't tied to
        a registered subscription. Returns True on a <400 response.
        """
        for attempt in range(1, self._max_attempts + 1):
            try:
                resp = await self._http.post(url, json=payload, timeout=self._timeout)
                if resp.status_code < 400:
                    return True
            except Exception:  # noqa: BLE001 - retry then give up
                pass
            if attempt < self._max_attempts:
                import asyncio

                await asyncio.sleep(self._base_backoff * attempt)
        return False

    async def on_event(self, event: DomainEvent) -> None:
        for sub in self._repo.list():
            if not sub.wants(event.type):
                continue
            await self._deliver_with_retry(sub, event)

    async def _deliver_with_retry(
        self, sub: WebhookSubscription, event: DomainEvent
    ) -> None:
        metrics = get_metrics()
        payload = {
            "type": event.type.value,
            "at": event.at.isoformat(),
            "subject_id": event.subject_id,
            "payload": event.payload,
        }
        for attempt in range(1, self._max_attempts + 1):
            record = DeliveryAttempt(attempt=attempt)
            try:
                resp = await self._http.post(
                    sub.url, json=payload, timeout=self._timeout
                )
                record.status_code = resp.status_code
                sub.last_status = resp.status_code
                sub.last_delivery_at = datetime.now(timezone.utc)
                if resp.status_code < 400:
                    record.success = True
                    sub.attempts_log.append(record)
                    metrics.webhook_deliveries.inc(result="ok")
                    return
                record.error = f"HTTP {resp.status_code}"
            except Exception as exc:
                record.error = str(exc)
                sub.last_status = None
                sub.last_delivery_at = datetime.now(timezone.utc)
            sub.attempts_log.append(record)
            sub.failure_count += 1
            metrics.webhook_deliveries.inc(result="error")
            if attempt < self._max_attempts:
                await asyncio.sleep(self._base_backoff * (2 ** (attempt - 1)))
        sub.dead_lettered = True
        metrics.webhook_deliveries.inc(result="dead_letter")
        log.warning("webhook %s dead-lettered after %d attempts",
                    sub.id, self._max_attempts)

    async def redrive(
        self, webhook_id: str, event: DomainEvent | None = None
    ) -> WebhookSubscription | None:
        """Re-activate a dead-lettered webhook and optionally re-deliver."""
        sub = self._repo.get(webhook_id)
        if sub is None:
            return None
        sub.dead_lettered = False
        sub.failure_count = 0
        if event is not None:
            await self._deliver_with_retry(sub, event)
        return sub
