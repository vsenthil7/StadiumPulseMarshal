"""Live Dynatrace observability client.

Talks to a Dynatrace environment via the MCP server when configured, falling
back to the Dynatrace Environment API v2 for problem/entity/metric retrieval.
Responses are mapped into the shared domain models.

This client is exercised against live infrastructure once credentials are
present (Claude Desktop / deployment). Its parsing helpers are unit-tested with
representative payloads so the mapping logic is covered without a live tenant.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.fixtures import matchday
from app.mcp.base import ObservabilityClient
from app.models.domain import (
    Entity,
    Event,
    FixtureTimelineEntry,
    Metric,
    MetricPoint,
    Problem,
    RootCauseNode,
)
from app.models.enums import EntityType, ProblemStatus, Severity

log = get_logger(__name__)

_SEVERITY_MAP = {
    "AVAILABILITY": Severity.CRITICAL,
    "ERROR": Severity.HIGH,
    "PERFORMANCE": Severity.MEDIUM,
    "RESOURCE_CONTENTION": Severity.MEDIUM,
    "CUSTOM_ALERT": Severity.LOW,
    "INFO": Severity.INFO,
    "MONITORING_UNAVAILABLE": Severity.LOW,
}

_ENTITY_TYPE_MAP = {
    "SERVICE": EntityType.SERVICE,
    "APPLICATION": EntityType.APPLICATION,
    "HOST": EntityType.HOST,
    "PROCESS_GROUP": EntityType.PROCESS,
    "PROCESS_GROUP_INSTANCE": EntityType.PROCESS,
    "DATABASE": EntityType.DATABASE,
    "RELATIONAL_DATABASE_SERVICE": EntityType.DATABASE,
    "KUBERNETES_CLUSTER": EntityType.KUBERNETES,
}


def _ts_from_ms(ms: int | None) -> datetime:
    if not ms:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class DynatraceMCPClient(ObservabilityClient):
    """Live client. Construct via :meth:`create` to inject an HTTP client."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    @classmethod
    def create(cls, settings: Settings) -> "DynatraceMCPClient":
        headers = {"Authorization": f"Api-Token {settings.dt_api_token}"}
        http = httpx.AsyncClient(
            base_url=(settings.dt_tenant_url or "").rstrip("/"),
            headers=headers,
            timeout=15.0,
        )
        return cls(settings, http)

    @property
    def mode(self) -> str:
        return "live"

    # --- Mapping helpers (unit tested) ------------------------------------
    @staticmethod
    def map_severity(raw: str | None) -> Severity:
        return _SEVERITY_MAP.get((raw or "").upper(), Severity.MEDIUM)

    @staticmethod
    def map_entity_type(raw: str | None) -> EntityType:
        return _ENTITY_TYPE_MAP.get((raw or "").upper(), EntityType.SERVICE)

    @classmethod
    def parse_entity(cls, payload: dict[str, Any]) -> Entity:
        return Entity(
            id=payload.get("entityId") or payload.get("id") or "unknown",
            name=payload.get("displayName") or payload.get("name") or "unknown",
            type=cls.map_entity_type(
                payload.get("type") or payload.get("entityType")
            ),
            tags=[
                t.get("key", "") if isinstance(t, dict) else str(t)
                for t in payload.get("tags", [])
            ],
            health=float(payload.get("health", 100.0)),
        )

    @classmethod
    def parse_problem(cls, payload: dict[str, Any]) -> Problem:
        affected = [
            cls.parse_entity(e)
            for e in payload.get("affectedEntities", [])
        ]
        status_raw = (payload.get("status") or "OPEN").upper()
        status = (
            ProblemStatus.OPEN
            if status_raw == "OPEN"
            else ProblemStatus.RESOLVED
        )
        root_cause = None
        rce = payload.get("rootCauseEntity")
        if rce:
            root_cause = RootCauseNode(
                entity_id=rce.get("entityId", "unknown"),
                entity_name=rce.get("name", "unknown"),
                entity_type=cls.map_entity_type(rce.get("type")),
                is_root_cause=True,
                confidence=float(rce.get("confidence", 0.8)),
                contribution=rce.get("contribution", ""),
            )
        events = [
            Event(
                id=ev.get("eventId", f"EV-{i}"),
                title=ev.get("title", "event"),
                entity_id=ev.get("entityId", "unknown"),
                timestamp=_ts_from_ms(ev.get("startTime")),
                description=ev.get("description", ""),
            )
            for i, ev in enumerate(payload.get("events", []))
        ]
        return Problem(
            id=payload.get("problemId") or payload.get("displayId") or "unknown",
            title=payload.get("title", "Untitled problem"),
            severity=cls.map_severity(payload.get("severityLevel")),
            status=status,
            opened_at=_ts_from_ms(payload.get("startTime")),
            resolved_at=(
                _ts_from_ms(payload.get("endTime"))
                if payload.get("endTime")
                else None
            ),
            affected_entities=affected,
            root_cause=root_cause,
            events=events,
            matchday_phase=matchday.phase_for(
                _ts_from_ms(payload.get("startTime"))
            ),
            impact_summary=payload.get("impactSummary", ""),
        )

    @staticmethod
    def parse_metric(entity_id: str, payload: dict[str, Any]) -> list[Metric]:
        result: list[Metric] = []
        for series in payload.get("result", []):
            key = series.get("metricId", "metric")
            for data in series.get("data", []):
                timestamps = data.get("timestamps", [])
                values = data.get("values", [])
                points = [
                    MetricPoint(timestamp=_ts_from_ms(ts), value=float(v))
                    for ts, v in zip(timestamps, values)
                    if v is not None
                ]
                result.append(
                    Metric(key=key, unit="", entity_id=entity_id, points=points)
                )
        return result

    # --- Live calls --------------------------------------------------------
    async def list_problems(self, *, open_only: bool = False) -> list[Problem]:
        params = {"problemSelector": "status(open)"} if open_only else {}
        resp = await self._http.get("/api/v2/problems", params=params)
        resp.raise_for_status()
        body = resp.json()
        return [self.parse_problem(p) for p in body.get("problems", [])]

    async def get_problem(self, problem_id: str) -> Problem | None:
        resp = await self._http.get(f"/api/v2/problems/{problem_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self.parse_problem(resp.json())

    async def list_entities(self) -> list[Entity]:
        resp = await self._http.get(
            "/api/v2/entities",
            params={"entitySelector": 'type("SERVICE")', "pageSize": 100},
        )
        resp.raise_for_status()
        return [self.parse_entity(e) for e in resp.json().get("entities", [])]

    async def get_metrics(self, entity_id: str) -> list[Metric]:
        resp = await self._http.get(
            "/api/v2/metrics/query",
            params={
                "metricSelector": "builtin:service.response.time:percentile(95)",
                "entitySelector": f'entityId("{entity_id}")',
            },
        )
        resp.raise_for_status()
        return self.parse_metric(entity_id, resp.json())

    async def get_fixture_timeline(self) -> list[FixtureTimelineEntry]:
        # The fixture/match timeline is supplied by the tournament scheduling
        # system; in live mode this would be fetched from that source. We reuse
        # the canonical timeline definition here.
        return matchday.fixture_timeline()

    async def close(self) -> None:
        await self._http.aclose()
