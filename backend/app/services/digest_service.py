"""Burn / suppression digest.

Composes a periodic operational summary — current page/ticket burn alerts, active
acknowledgements/silences, and the suppression ratio — and dispatches it to a
notification channel on an interval. Useful as a shift-handover or hourly
heads-up. Gated by config; the scheduler mirrors PruneScheduler (idempotent
start, clean stop, survives errors).
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.core.logging import get_logger

log = get_logger(__name__)


_SEV_RANK = {"none": 0, "ticket": 1, "page": 2}


async def compose_digest(ctx, window_hours: float = 24.0,
                         min_severity: str = "ticket") -> str:
    """Build a human-readable burn/suppression digest from current state.

    ``min_severity`` filters the active-alert lines (page > ticket); the
    suppression ratio is computed over ``window_hours`` of counter history when
    available, else lifetime totals.
    """
    min_rank = _SEV_RANK.get(min_severity, 1)
    alerts = await ctx.burn_alerts()  # cross-venue (system digest)

    def _sev(a):
        return getattr(a.severity, "value", a.severity)

    shown = [a for a in alerts if _SEV_RANK.get(_sev(a), 0) >= min_rank]
    page = sum(1 for a in shown if _sev(a) == "page")
    ticket = sum(1 for a in shown if _sev(a) == "ticket")
    active = await ctx.burn_acks.active_summary()
    totals = await ctx.burn_counters.totals()
    acks = totals.get("ack", 0)
    sils = totals.get("silence", 0)
    denom = acks + sils
    ratio = round(100 * sils / denom) if denom else 0
    lines = [
        "StadiumPulse burn digest",
        f"- Window: {window_hours:g}h, min severity: {min_severity}",
        f"- Active alerts: {page} page, {ticket} ticket",
        f"- Active state: {len(active['acks'])} acknowledged, "
        f"{len(active['silences'])} silenced",
        f"- Lifetime response: {acks} acks, {sils} silences "
        f"(suppression {ratio}%)",
    ]
    if shown:
        worst = max(shown, key=lambda a: a.burn_rate)
        lines.append(
            f"- Hottest: {worst.slo_name} at {worst.burn_rate:g}x "
            f"({_sev(worst)})"
        )
    return "\n".join(lines)


class DigestScheduler:
    """Periodically composes and dispatches the digest. Idempotent start/stop."""

    def __init__(self, ctx, interval_seconds: float,
                 dispatch: Callable[[str], Awaitable[None]] | None = None,
                 window_hours: float = 24.0, min_severity: str = "ticket") -> None:
        self._ctx = ctx
        self._interval = interval_seconds
        self._dispatch = dispatch
        self._window_hours = window_hours
        self._min_severity = min_severity
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                msg = await compose_digest(
                    self._ctx, self._window_hours, self._min_severity)
                if self._dispatch is not None:
                    await self._dispatch(msg)
                else:
                    log.info("Burn digest:\n%s", msg)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - never let the loop die
                log.warning("digest cycle failed: %s", exc)
