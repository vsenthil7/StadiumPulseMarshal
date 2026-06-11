"""On-call schedule sources.

The on-call directory needs to know *who is on-call now* per tier, not just a
static roster. A ``ScheduleSource`` resolves the current on-call engineer for
each escalation tier, optionally rotating by time so different engineers hold the
pager on different shifts.

Implementations:
- ``StaticScheduleSource`` — the fixed default roster (one engineer per tier).
- ``RotatingScheduleSource`` — rotates a pool of engineers per tier on a fixed
  shift cadence (e.g. 12h shifts), so the resolved roster changes with the clock.
- ``ExternalScheduleSource`` — PagerDuty/Opsgenie-shaped adapter that pulls the
  current on-calls from a schedule API, mapping each schedule to a tier, with a
  graceful fallback to a static source on any error.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.incident import EscalationTier
from app.models.notification import OnCallEngineer

log = get_logger(__name__)


class ScheduleSource(Protocol):
    async def current_roster(self, now: float | None = None) -> list[OnCallEngineer]:
        """Return the engineer on-call for each tier at ``now``."""
        ...


class StaticScheduleSource:
    def __init__(self, roster: list[OnCallEngineer]) -> None:
        self._roster = roster

    async def current_roster(self, now: float | None = None) -> list[OnCallEngineer]:
        return list(self._roster)


@dataclass
class RotatingScheduleSource:
    """Rotates a pool of engineers per tier on a fixed shift cadence.

    ``pools`` maps a tier to an ordered list of engineers; the one on-call is
    selected by ``(epoch // shift_seconds) % len(pool)`` so the rotation is
    deterministic and advances each shift. A tier with a single-engineer pool
    behaves like the static roster.
    """

    pools: dict[EscalationTier, list[OnCallEngineer]]
    shift_seconds: float = 12 * 3600  # 12-hour shifts

    async def current_roster(self, now: float | None = None) -> list[OnCallEngineer]:
        now = time.time() if now is None else now
        shift = int(now // self.shift_seconds)
        out: list[OnCallEngineer] = []
        for tier, pool in self.pools.items():
            if not pool:
                continue
            out.append(pool[shift % len(pool)])
        return out

    def next_handoff(self, now: float | None = None) -> float:
        now = time.time() if now is None else now
        return (int(now // self.shift_seconds) + 1) * self.shift_seconds

    def pool_view(self, now: float | None = None) -> list[dict]:
        """Per-tier rotation view: current holder + who is next."""
        now = time.time() if now is None else now
        shift = int(now // self.shift_seconds)
        out: list[dict] = []
        for tier, pool in self.pools.items():
            if not pool:
                continue
            cur = pool[shift % len(pool)]
            nxt = pool[(shift + 1) % len(pool)]
            out.append({
                "tier": tier.value,
                "current": {"id": cur.id, "name": cur.name, "handle": cur.handle},
                "next": {"id": nxt.id, "name": nxt.name, "handle": nxt.handle},
                "pool_size": len(pool),
            })
        return out


class ExternalScheduleSource:
    """PagerDuty/Opsgenie-shaped adapter.

    Pulls current on-calls from a schedule API (``/oncalls`` style) and maps each
    schedule id to an escalation tier via ``schedule_tier_map``. Any error falls
    back to the supplied static source so resolution never hard-fails.
    """

    def __init__(self, settings: Settings, fallback: ScheduleSource,
                 http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._fallback = fallback
        self._http = http

    async def current_roster(self, now: float | None = None) -> list[OnCallEngineer]:
        base = (self._settings.oncall_api_url or "").rstrip("/")
        token = self._settings.oncall_api_token
        if not base or not token:
            return await self._fallback.current_roster(now)
        owns = self._http is None
        http = self._http or httpx.AsyncClient(timeout=5.0)
        try:
            r = await http.get(
                f"{base}/oncalls",
                headers={"Authorization": f"Token token={token}"},
            )
            r.raise_for_status()
            engineers = _parse_oncalls(r.json(), self._settings.oncall_schedule_tier_mapping)
            if not engineers:
                return await self._fallback.current_roster(now)
            return engineers
        except Exception as exc:  # noqa: BLE001 - optional source, never fatal
            log.warning("On-call schedule fetch failed; using fallback: %s", exc)
            return await self._fallback.current_roster(now)
        finally:
            if owns:
                await http.aclose()


_TIER_BY_NAME = {t.value: t for t in EscalationTier}


def _parse_oncalls(data: dict, schedule_tier_map: dict[str, str]) -> list[OnCallEngineer]:
    """Convert a PagerDuty-shaped ``oncalls`` payload to on-call engineers.

    Expects ``oncalls[].{schedule.id, user.{summary,email}, escalation_level}``.
    A schedule id present in ``schedule_tier_map`` pins the tier; otherwise the
    escalation_level (1/2/3) maps to TIER1/2/3.
    """
    out: dict[EscalationTier, OnCallEngineer] = {}
    for oc in data.get("oncalls", []):
        sched = (oc.get("schedule") or {}).get("id", "")
        user = oc.get("user") or {}
        name = user.get("summary") or user.get("name") or "On-call"
        email = user.get("email") or ""
        level = oc.get("escalation_level")
        tier_name = schedule_tier_map.get(sched)
        if tier_name is None and level in (1, 2, 3):
            tier_name = f"TIER{level}"
        tier = _TIER_BY_NAME.get(tier_name or "")
        if tier is None or tier in out:
            continue
        out[tier] = OnCallEngineer(
            id=f"PD-{sched or name}", name=name, tier=tier,
            handle=email or name, channels=["pagerduty", "email"],
        )
    return list(out.values())


def build_schedule_source(
    settings: Settings, default_roster: list[OnCallEngineer],
    pools: dict[EscalationTier, list[OnCallEngineer]] | None = None,
) -> ScheduleSource:
    static = StaticScheduleSource(default_roster)
    if settings.oncall_api_url and settings.oncall_api_token:
        return ExternalScheduleSource(settings, fallback=static)
    if settings.oncall_rotation_enabled and pools:
        return RotatingScheduleSource(
            pools=pools, shift_seconds=settings.oncall_shift_hours * 3600,
        )
    return static
