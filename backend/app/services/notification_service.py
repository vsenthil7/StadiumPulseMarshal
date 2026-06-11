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
    NotificationStatus,
)
from app.repositories.base import NotificationRepository

log = get_logger(__name__)


def _new_id() -> str:
    return f"NTF-{uuid.uuid4().hex[:8]}"


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
