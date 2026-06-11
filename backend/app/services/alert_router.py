"""Real alert delivery: PagerDuty Events v2 + OpsGenie Alerts API.

Both senders are optional; the router degrades to log-only when credentials are
absent (``USE_MOCKS`` mode or simply unconfigured). Burn-alert notifications
produced by ``NotificationService`` can be routed here when the relevant
settings are present.

PagerDuty: set ``PAGERDUTY_ROUTING_KEY`` → POST https://events.pagerduty.com/v2/enqueue
OpsGenie:  set ``OPSGENIE_API_KEY``      → POST https://api.opsgenie.com/v2/alerts

The router accepts an injected ``httpx.AsyncClient`` so tests can supply a
``MockTransport``; it never raises on delivery failure (returns False instead),
so alerting can't take down the request path.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.logging import get_logger
from app.models.notification import Notification, NotificationChannel

log = get_logger(__name__)

_PD_ENDPOINT = "https://events.pagerduty.com/v2/enqueue"
_OG_ENDPOINT = "https://api.opsgenie.com/v2/alerts"

_PD_SEVERITY = {"page": "critical", "ticket": "warning", "digest": "info"}


class AlertRouter:
    """Dispatches notifications to external alerting platforms."""

    def __init__(
        self,
        pagerduty_routing_key: str | None = None,
        opsgenie_api_key: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._pd_key = pagerduty_routing_key
        self._og_key = opsgenie_api_key
        self._http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None

    @property
    def configured(self) -> bool:
        return bool(self._pd_key or self._og_key)

    async def dispatch(self, notification: Notification) -> bool:
        """Route a notification to the appropriate external platform.

        Returns True if an external delivery succeeded. Falls back to log-only
        (returns False) when no credentials are configured for the channel.
        """
        channel = notification.channel
        if channel == NotificationChannel.PAGERDUTY and self._pd_key:
            return await self._pagerduty(notification)
        if channel == NotificationChannel.SLACK:
            # Slack delivery is handled by the digest webhook / ChatOps module;
            # log here so the notification record reflects routing intent.
            log.info("Slack alert queued for %s: %s",
                     notification.recipient, notification.subject)
            return True
        # OpsGenie as a secondary sender for any non-PD alert.
        if self._og_key:
            return await self._opsgenie(notification)
        log.info("Alert dispatch (no credentials): %s — %s",
                 getattr(channel, "value", channel), notification.subject)
        return False

    async def _pagerduty(self, notification: Notification) -> bool:
        sev = _PD_SEVERITY.get((notification.severity or "").lower(), "warning")
        payload: dict[str, Any] = {
            "routing_key": self._pd_key,
            "event_action": "trigger",
            "dedup_key": notification.id,
            "payload": {
                "summary": notification.subject,
                "source": "stadiumpulse-marshal",
                "severity": sev,
                "custom_details": {
                    "body": notification.body,
                    "incident_id": notification.incident_id,
                    "venue_id": notification.venue_id,
                    "channel": getattr(notification.channel, "value",
                                       notification.channel),
                },
            },
        }
        try:
            resp = await self._http.post(
                _PD_ENDPOINT, content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            ok = resp.status_code < 400
            log.info("PagerDuty dispatch %s (status=%s)",
                     "ok" if ok else "failed", resp.status_code)
            return ok
        except Exception as exc:  # noqa: BLE001
            log.error("PagerDuty dispatch error: %s", exc)
            return False

    async def _opsgenie(self, notification: Notification) -> bool:
        priority = "P1" if (notification.severity or "").lower() == "page" else "P3"
        payload: dict[str, Any] = {
            "message": notification.subject,
            "alias": notification.id,
            "description": notification.body,
            "priority": priority,
            "source": "stadiumpulse-marshal",
            "details": {
                "incident_id": notification.incident_id or "",
                "venue_id": notification.venue_id or "",
            },
        }
        try:
            resp = await self._http.post(
                _OG_ENDPOINT, json=payload,
                headers={"Authorization": f"GenieKey {self._og_key}",
                         "Content-Type": "application/json"},
            )
            ok = resp.status_code < 400
            log.info("OpsGenie dispatch %s (status=%s)",
                     "ok" if ok else "failed", resp.status_code)
            return ok
        except Exception as exc:  # noqa: BLE001
            log.error("OpsGenie dispatch error: %s", exc)
            return False

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()


def build_alert_router(settings, http: httpx.AsyncClient | None = None) -> AlertRouter:
    """Construct an AlertRouter from settings (creds optional)."""
    return AlertRouter(
        pagerduty_routing_key=getattr(settings, "pagerduty_routing_key", None),
        opsgenie_api_key=getattr(settings, "opsgenie_api_key", None),
        http=http,
    )
