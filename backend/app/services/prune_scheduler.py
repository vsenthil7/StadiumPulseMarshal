"""Background prune scheduler.

Periodically sweeps expired/consumed/revoked refresh tokens so the store doesn't
grow unbounded. Runs as an asyncio task for the app's lifespan; start/stop are
idempotent and shutdown is clean (the task is cancelled and awaited).
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.core.logging import get_logger

log = get_logger(__name__)


class PruneScheduler:
    def __init__(
        self,
        prune: Callable[[], Awaitable[int]],
        interval_seconds: float = 3600.0,
        *,
        run_immediately: bool = False,
    ) -> None:
        self._prune = prune
        self.interval = interval_seconds
        self._run_immediately = run_immediately
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return  # already running (idempotent)
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        try:
            if self._run_immediately:
                await self._sweep()
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                except asyncio.TimeoutError:
                    await self._sweep()
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise

    async def _sweep(self) -> None:
        try:
            removed = await self._prune()
            if removed:
                log.info("Pruned %d expired/consumed refresh tokens", removed)
        except Exception as exc:  # noqa: BLE001 - never let the loop die
            log.warning("Refresh-token prune failed: %s", exc)
