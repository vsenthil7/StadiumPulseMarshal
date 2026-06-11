"""Notification service.

Builds and dispatches notifications for incidents. In mock mode dispatch simply
marks them SENT and records them; in live mode a channel sender would be plugged
in here (email/SMS/Slack/PagerDuty/webhook). The interface stays the same.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.models.incident import Incident
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationSource,
    NotificationStatus,
)
from app.repositories.base import NotificationRepository

log = get_logger(__name__)


def _new_id() -> str:
    return f"NTF-{uuid.uuid4().hex[:8]}"


# Burn-alert severity → channels. Page wakes on-call (PagerDuty + SMS); ticket
# files asynchronously (email + Slack). A real deployment maps recipients to an
# on-call directory; here we route to representative addresses per channel.
_BURN_ROUTING: dict[str, list[tuple[NotificationChannel, str]]] = {
    "page": [
        (NotificationChannel.PAGERDUTY, "oncall-sre"),
        (NotificationChannel.SMS, "+10000000000"),
    ],
    "ticket": [
        (NotificationChannel.EMAIL, "sre@stadiumpulse.demo"),
        (NotificationChannel.SLACK, "#slo-alerts"),
    ],
}


class NotificationService:
    def __init__(self, repo: NotificationRepository) -> None:
        self._repo = repo

    async def notify(
        self,
        incident: Incident,
        *,
        channel: NotificationChannel,
        recipient: str,
        subject: str,
        body: str,
    ) -> Notification:
        notification = Notification(
            id=_new_id(),
            incident_id=incident.id,
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
        )
        await self._repo.add(notification)
        # Dispatch (mock: immediate success).
        notification.status = NotificationStatus.SENT
        notification.sent_at = datetime.now(timezone.utc)
        await self._repo.update(notification)
        log.info(
            "Notification %s -> %s via %s for incident %s",
            notification.id,
            recipient,
            channel.value,
            incident.id,
        )
        return notification

    async def list_for_incident(self, incident_id: str) -> list[Notification]:
        return await self._repo.list(incident_id=incident_id)

    async def list_all(self) -> list[Notification]:
        return await self._repo.list()

    async def _dispatch(self, n: Notification) -> Notification:
        await self._repo.add(n)
        n.status = NotificationStatus.SENT
        n.sent_at = datetime.now(timezone.utc)
        await self._repo.update(n)
        return n

    async def notify_burn_alert(self, alert) -> list[Notification]:
        """Route a burn-rate alert to the channels for its severity.

        Deduplicates within the alert's window so a sustained burn doesn't spam:
        if an un-expired notification already exists for this (slo_id, severity),
        no new one is sent. Returns the notifications created (possibly empty).
        """
        severity = alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity)
        routes = _BURN_ROUTING.get(severity, [])
        if not routes:
            return []

        # Dedupe: look for a recent notification for the same SLO+severity.
        existing = await self._repo.list()
        marker = f"[burn:{alert.slo_id}:{severity}]"
        for prev in existing:
            if prev.source == NotificationSource.BURN_ALERT and marker in prev.subject:
                # Suppress within the short window of the tier to avoid spam.
                age = (datetime.now(timezone.utc) - prev.created_at).total_seconds()
                if age < alert.short_window_hours * 3600:
                    return []

        created: list[Notification] = []
        for channel, recipient in routes:
            n = Notification(
                id=_new_id(),
                incident_id=None,
                source=NotificationSource.BURN_ALERT,
                severity=severity,
                venue_id=getattr(alert, "venue_id", None),
                channel=channel,
                recipient=recipient,
                subject=f"{marker} {alert.slo_name} burning at {alert.burn_rate:g}x",
                body=alert.message,
            )
            created.append(await self._dispatch(n))
        log.info(
            "Burn alert %s (%s) routed to %d channel(s)",
            alert.slo_id, severity, len(created),
        )
        return created
