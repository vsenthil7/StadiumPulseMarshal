"""Change-event service: record changes, correlate with incidents by time."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.core.logging import get_logger
from app.models.change_event import ChangeEvent, ChangeType

log = get_logger(__name__)


def _id() -> str:
    return f"CHG-{uuid.uuid4().hex[:8]}"


class ChangeEventService:
    """In-memory change log with simple time-proximity incident correlation."""

    def __init__(self, correlation_window_minutes: float = 60.0) -> None:
        self._events: dict[str, ChangeEvent] = {}
        self._window = correlation_window_minutes

    def record(self, event: ChangeEvent) -> ChangeEvent:
        if not event.id:
            event = event.model_copy(update={"id": _id()})
        self._events[event.id] = event
        log.info("Change event recorded: %s (%s)", event.id, event.title)
        return event

    def list(self, service_id: str | None = None,
             change_type: ChangeType | None = None) -> list[ChangeEvent]:
        out = list(self._events.values())
        if service_id:
            out = [e for e in out if e.service_id == service_id]
        if change_type:
            out = [e for e in out if e.change_type == change_type]
        return sorted(out, key=lambda e: e.at, reverse=True)

    def get(self, event_id: str) -> ChangeEvent | None:
        return self._events.get(event_id)

    def link_incident(self, event_id: str, incident_id: str) -> ChangeEvent | None:
        e = self._events.get(event_id)
        if e is None:
            return None
        if incident_id not in e.linked_incident_ids:
            e = e.model_copy(update={
                "linked_incident_ids": [*e.linked_incident_ids, incident_id]})
            self._events[event_id] = e
        return e

    def correlate(self, incident_time: datetime, service_id: str | None = None,
                  venue_id: str | None = None) -> list[ChangeEvent]:
        """Return change events within the correlation window before an incident."""
        window = timedelta(minutes=self._window)
        lo = incident_time - window
        out = []
        for e in self._events.values():
            if not (lo <= e.at <= incident_time):
                continue
            if service_id and e.service_id and e.service_id != service_id:
                continue
            if venue_id and e.venue_id and e.venue_id != venue_id:
                continue
            out.append(e)
        return sorted(out, key=lambda e: e.at, reverse=True)
