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


async def compose_venue_digest(ctx, venue_id: str) -> str:
    """A burn digest scoped to a single venue."""
    alerts = [a for a in await ctx.burn_alerts()
              if (a.venue_id or "unassigned") == venue_id]
    page = sum(1 for a in alerts
               if getattr(a.severity, "value", a.severity) == "page")
    ticket = sum(1 for a in alerts
                 if getattr(a.severity, "value", a.severity) == "ticket")
    totals = await ctx.burn_counters.totals(venue_id)
    acks = totals.get("ack", 0)
    sils = totals.get("silence", 0)
    denom = acks + sils
    ratio = round(100 * sils / denom) if denom else 0
    short = venue_id.replace("venue_", "")
    lines = [
        f"StadiumPulse burn digest — {short}",
        f"- Active alerts: {page} page, {ticket} ticket",
        f"- Response: {acks} acks, {sils} silences (suppression {ratio}%)",
    ]
    if alerts:
        worst = max(alerts, key=lambda a: a.burn_rate)
        lines.append(
            f"- Hottest: {worst.slo_name} at {worst.burn_rate:g}x "
            f"({getattr(worst.severity, 'value', worst.severity)})")
    return "\n".join(lines)


async def compose_daily_digest(ctx) -> str:
    """A 24h rollup digest: lifetime response totals, suppression, active state,
    and the venues with the most burn pressure. Distinct from the hourly
    heads-up — meant as an end-of-day summary."""
    totals = await ctx.burn_counters.totals()
    acks = totals.get("ack", 0)
    sils = totals.get("silence", 0)
    denom = acks + sils
    ratio = round(100 * sils / denom) if denom else 0
    active = await ctx.burn_acks.active_summary()
    alerts = await ctx.burn_alerts()
    # rank venues by current page+ticket pressure
    by_venue: dict[str, int] = {}
    for a in alerts:
        vid = a.venue_id or "unassigned"
        by_venue[vid] = by_venue.get(vid, 0) + 1
    top = sorted(by_venue.items(), key=lambda kv: kv[1], reverse=True)[:3]
    lines = [
        "StadiumPulse daily burn summary (24h)",
        f"- Response: {acks} acks, {sils} silences (suppression {ratio}%)",
        f"- Currently: {len(active['acks'])} acknowledged, "
        f"{len(active['silences'])} silenced",
        f"- Active alerts: {len(alerts)}",
    ]
    if top:
        lines.append("- Top venues: " +
                     ", ".join(f"{v.replace('venue_', '')} ({n})" for v, n in top))
    return "\n".join(lines)


_SEV_RANK = {"none": 0, "ticket": 1, "page": 2}


def next_run_delay(hh_mm: str, now_epoch: float | None = None,
                   tz: str | None = None) -> float:
    """Seconds until the next occurrence of ``HH:MM`` in timezone ``tz``.

    ``tz`` is an IANA name (e.g. "Europe/London"); when omitted, the server's
    local time is used. If the time has already passed today, returns the delay
    until tomorrow.
    """
    import time as _t
    from datetime import datetime

    now = _t.time() if now_epoch is None else now_epoch
    try:
        hh, mm = (int(x) for x in hh_mm.split(":"))
    except (ValueError, AttributeError):
        hh, mm = 9, 0

    tzinfo = None
    if tz:
        try:
            from zoneinfo import ZoneInfo

            tzinfo = ZoneInfo(tz)
        except Exception:  # noqa: BLE001 - bad tz name → fall back to local
            tzinfo = None

    dt = datetime.fromtimestamp(now, tzinfo)
    since_midnight = dt.hour * 3600 + dt.minute * 60 + dt.second
    target = hh * 3600 + mm * 60
    delay = target - since_midnight
    if delay <= 0:
        delay += 86400
    return float(delay)


class SchedulerStats:
    """Mixin: lightweight run bookkeeping shared by the digest schedulers."""

    name: str = "scheduler"

    def _init_stats(self) -> None:
        self._last_run: float | None = None
        self._last_status: str = "idle"
        self._runs: int = 0
        self._next_wake: float | None = None

    def _record_run(self, ok: bool) -> None:
        import time as _t

        self._last_run = _t.time()
        self._last_status = "ok" if ok else "error"
        self._runs += 1

    def next_run_epoch(self) -> float | None:
        return None  # overridden where a deterministic next time exists

    def status(self) -> dict:
        running = getattr(self, "_task", None) is not None and not self._task.done()
        return {
            "name": self.name,
            "running": running,
            "last_run_epoch": getattr(self, "_last_run", None),
            "last_status": getattr(self, "_last_status", "idle"),
            "runs": getattr(self, "_runs", 0),
            "next_run_epoch": self.next_run_epoch(),
        }


class DailyAtScheduler(SchedulerStats):
    """Runs a composer+dispatch once per day at a wall-clock ``HH:MM``."""

    name = "daily_digest"

    def __init__(self, ctx, at: str, composer, dispatch, tz: str | None = None) -> None:
        self._ctx = ctx
        self._at = at
        self._composer = composer
        self._dispatch = dispatch
        self._tz = tz
        self._task = None
        self._init_stats()

    def next_run_epoch(self) -> float | None:
        import time as _t

        return _t.time() + next_run_delay(self._at, tz=self._tz)

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
                await asyncio.sleep(next_run_delay(self._at, tz=self._tz))
                msg = await self._composer(self._ctx)
                if self._dispatch is not None:
                    await self._dispatch(msg)
                else:
                    log.info("Daily burn digest:\n%s", msg)
                self._record_run(True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._record_run(False)
                log.warning("daily digest cycle failed: %s", exc)


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


class DigestScheduler(SchedulerStats):
    """Periodically composes and dispatches the digest. Idempotent start/stop."""

    name = "hourly_digest"

    def __init__(self, ctx, interval_seconds: float,
                 dispatch: Callable[[str], Awaitable[None]] | None = None,
                 window_hours: float = 24.0, min_severity: str = "ticket",
                 composer: Callable[..., Awaitable[str]] | None = None) -> None:
        self._ctx = ctx
        self._interval = interval_seconds
        self._dispatch = dispatch
        self._window_hours = window_hours
        self._min_severity = min_severity
        self._composer = composer
        self._task: asyncio.Task | None = None
        self._init_stats()

    def next_run_epoch(self) -> float | None:
        import time as _t

        # Real next-wake once the loop is sleeping; estimate before first sleep.
        return self._next_wake if self._next_wake is not None \
            else _t.time() + self._interval

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
                import time as _t
                self._next_wake = _t.time() + self._interval
                await asyncio.sleep(self._interval)
                if self._composer is not None:
                    msg = await self._composer(self._ctx)
                else:
                    msg = await compose_digest(
                        self._ctx, self._window_hours, self._min_severity)
                if self._dispatch is not None:
                    await self._dispatch(msg)
                else:
                    log.info("Burn digest:\n%s", msg)
                self._record_run(True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - never let the loop die
                self._record_run(False)
                log.warning("digest cycle failed: %s", exc)


class VenueFanoutScheduler(SchedulerStats):
    """Periodically composes a per-venue digest for each mapped venue and
    dispatches it to that venue's channel, skipping muted venues.

    ``venue_channels`` maps venue_id → recipient; ``dispatch`` receives
    (venue_id, recipient, message). Idempotent start/stop like the others.
    """

    name = "venue_fanout"

    def __init__(self, ctx, interval_seconds: float, venue_channels: dict,
                 dispatch, mute_store=None) -> None:
        self._ctx = ctx
        self._interval = interval_seconds
        self._venue_channels = venue_channels
        self._dispatch = dispatch
        self._mute_store = mute_store
        self._task = None
        self._init_stats()

    def next_run_epoch(self) -> float | None:
        import time as _t

        # Real next-wake once the loop is sleeping; estimate before first sleep.
        return self._next_wake if self._next_wake is not None \
            else _t.time() + self._interval

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

    async def run_once(self) -> list[str]:
        """Compose+dispatch for each mapped, unmuted venue. Returns venues sent."""
        sent: list[str] = []
        for venue_id, recipient in self._venue_channels.items():
            if self._mute_store is not None and await self._mute_store.is_muted(venue_id):
                continue
            msg = await compose_venue_digest(self._ctx, venue_id)
            if self._dispatch is not None:
                await self._dispatch(venue_id, recipient, msg)
            sent.append(venue_id)
        return sent

    async def _run(self) -> None:
        while True:
            try:
                import time as _t
                self._next_wake = _t.time() + self._interval
                await asyncio.sleep(self._interval)
                await self.run_once()
                self._record_run(True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._record_run(False)
                log.warning("venue fan-out cycle failed: %s", exc)
