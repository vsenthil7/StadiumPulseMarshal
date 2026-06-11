"""Management-zone → venue sources: static, live Dynatrace, and fallback."""
from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.services.zone_source import (
    DynatraceZoneSource,
    StaticZoneSource,
    build_zone_source,
)

ZONE_MAP = "Arena North=venue_arena_north,Olympic Park=venue_olympic_park"


@pytest.mark.asyncio
async def test_static_source_returns_config_map():
    s = StaticZoneSource(Settings(venue_zone_map=ZONE_MAP))
    m = await s.zone_to_venue()
    assert m["Arena North"] == "venue_arena_north"
    assert m["Olympic Park"] == "venue_olympic_park"


def test_build_zone_source_picks_static_without_tenant():
    src = build_zone_source(Settings(venue_zone_map=ZONE_MAP))
    assert isinstance(src, StaticZoneSource)


def test_build_zone_source_picks_live_with_tenant():
    src = build_zone_source(Settings(
        dt_tenant_url="https://abc.live.dynatrace.com",
        dt_api_token="dt0c01.xxx",
        venue_zone_map=ZONE_MAP,
    ))
    assert isinstance(src, DynatraceZoneSource)


@pytest.mark.asyncio
async def test_live_source_pulls_zones_from_api():
    settings = Settings(
        dt_tenant_url="https://abc.live.dynatrace.com",
        dt_api_token="dt0c01.xxx",
        venue_zone_map=ZONE_MAP,
    )

    def handler(req: httpx.Request) -> httpx.Response:
        assert "managementZones" in str(req.url)
        assert req.headers.get("Authorization", "").startswith("Api-Token ")
        return httpx.Response(200, json={
            "values": [{"id": "1", "name": "Arena North"},
                       {"id": "2", "name": "Olympic Park"}]
        })

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        src = DynatraceZoneSource(settings, http=http)
        m = await src.zone_to_venue()
        assert m["Arena North"] == "venue_arena_north"
        assert m["Olympic Park"] == "venue_olympic_park"
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_live_source_falls_back_to_static_on_api_error():
    settings = Settings(
        dt_tenant_url="https://abc.live.dynatrace.com",
        dt_api_token="dt0c01.xxx",
        venue_zone_map=ZONE_MAP,
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        src = DynatraceZoneSource(settings, http=http)
        m = await src.zone_to_venue()
        # falls back to the static config map
        assert m["Arena North"] == "venue_arena_north"
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_live_source_static_overrides_win():
    # A zone present in the API but also pinned in static config uses static.
    settings = Settings(
        dt_tenant_url="https://abc.live.dynatrace.com",
        dt_api_token="dt0c01.xxx",
        venue_zone_map="Arena North=venue_special",
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"values": [{"name": "Arena North"}]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        m = await DynatraceZoneSource(settings, http=http).zone_to_venue()
        assert m["Arena North"] == "venue_special"
    finally:
        await http.aclose()
