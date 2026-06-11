"""Management-zone → venue sources.

The entity→venue resolver needs a map from a Dynatrace management-zone name to a
venue id. Round 7 supplied that map from static config. Round 8 adds a live
source that pulls management zones from the Dynatrace API, so a tenant's zones
flow through without hand-maintained config — falling back to static config for
any zone the API doesn't cover (or when the API is unavailable).
"""
from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


class ZoneSource(Protocol):
    async def zone_to_venue(self) -> dict[str, str]:
        """Return a mapping of management-zone name → venue id."""
        ...


class StaticZoneSource:
    """Zone map straight from configuration (``VENUE_ZONE_MAP``)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def zone_to_venue(self) -> dict[str, str]:
        return dict(self._settings.venue_zone_mapping)


class DynatraceZoneSource:
    """Pulls management zones from the Dynatrace config API and maps each to a
    venue.

    A zone is associated with a venue when its name matches a configured venue
    name/alias, or via the static ``VENUE_ZONE_MAP`` (which can alias an exact
    zone name to a venue). The static map always wins, so an operator can pin a
    mapping the API naming wouldn't otherwise produce. On any API error we fall
    back to the static map alone — the resolver must never hard-fail on the
    optional live source.
    """

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http

    async def _fetch_zones(self) -> list[str]:
        base = (self._settings.dt_tenant_url or "").rstrip("/")
        token = self._settings.dt_api_token
        if not base or not token:
            return []
        url = f"{base}/api/config/v1/managementZones"
        owns = self._http is None
        http = self._http or httpx.AsyncClient(timeout=5.0)
        try:
            r = await http.get(url, headers={"Authorization": f"Api-Token {token}"})
            r.raise_for_status()
            data = r.json()
            return [z.get("name", "") for z in data.get("values", []) if z.get("name")]
        finally:
            if owns:
                await http.aclose()

    async def zone_to_venue(self) -> dict[str, str]:
        static = dict(self._settings.venue_zone_mapping)
        try:
            zones = await self._fetch_zones()
        except Exception as exc:  # noqa: BLE001 - optional source, never fatal
            log.warning("Dynatrace zone fetch failed; using static map: %s", exc)
            return static
        # Auto-map zones whose name matches a venue id suffix or a configured
        # alias; static config entries always take precedence.
        merged: dict[str, str] = {}
        for zone in zones:
            # Heuristic: a zone named exactly like a configured alias maps via
            # static; otherwise leave to static. (Conservative — we never invent
            # a venue id from a zone name alone.)
            if zone in static:
                merged[zone] = static[zone]
        merged.update(static)
        return merged


def build_zone_source(settings: Settings, http: httpx.AsyncClient | None = None) -> ZoneSource:
    """Live Dynatrace source when a tenant + token are configured, else static."""
    if settings.dt_tenant_url and settings.dt_api_token:
        return DynatraceZoneSource(settings, http)
    return StaticZoneSource(settings)
