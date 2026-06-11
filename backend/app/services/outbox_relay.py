"""Outbox relay.

Periodically (or on demand) drains PENDING outbox entries, publishes each to the
event bus, and marks it DISPATCHED. Because entries are persisted in the same
store as domain state, an event survives a crash between commit and delivery —
the relay re-reads it on the next run (at-least-once delivery).
"""
from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.events.bus import EventBus

log = get_logger(__name__)


class OutboxRelay:
    def __init__(self, repo, bus: EventBus, *, poll_interval: float = 1.0) -> None:
        self._repo = repo
        self._bus = bus
        self._poll = poll_interval
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    async def drain_once(self, *, limit: int = 100) -> int:
        """Publish all currently-pending entries; return the count delivered."""
        pending = await self._repo.list_pending(limit=limit)
        delivered = 0
        for entry in pending:
            try:
                await self._bus.publish(entry.to_event())
                await self._repo.mark_dispatched(entry.id)
                delivered += 1
            except Exception as exc:  # pragma: no cover - defensive
                await self._repo.mark_failed(entry.id, str(exc))
                log.warning("outbox relay failed for %s: %s", entry.id, exc)
        return delivered

    async def _loop(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.drain_once()
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("outbox relay loop error: %s", exc)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._poll)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        if self._task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - defensive (no running loop)
            # No running loop (e.g. constructed outside async context) — caller
            # will drive drain_once() manually. Nothing to start.
            return
        self._stopped.clear()
        self._task = loop.create_task(self._loop())

    async def stop(self) -> None:
        self._stopped.set()
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        try:
            # Only await if we're on the same loop the task belongs to.
            if task.get_loop() is asyncio.get_running_loop():
                await task
            else:  # pragma: no cover - cross-loop teardown safety
                task.cancel()
        except RuntimeError:  # pragma: no cover - no running loop
            task.cancel()
