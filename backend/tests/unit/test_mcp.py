"""Tests for MCP clients, parsing and factory."""
from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.mcp.dynatrace_client import DynatraceMCPClient
from app.mcp.factory import build_observability_client
from app.mcp.mock_client import MockMCPClient
from app.models.enums import EntityType, ProblemStatus, Severity


async def test_mock_client_problems():
    c = MockMCPClient()
    assert c.mode == "mock"
    allp = await c.list_problems()
    openp = await c.list_problems(open_only=True)
    assert len(allp) == 3
    assert len(openp) == 2
    assert await c.get_problem("P-2026-0613-001") is not None
    assert await c.get_problem("missing") is None
    assert len(await c.list_entities()) == 5
    metrics = await c.get_metrics("DB-PAYMENTS")
    assert metrics[0].key == "entity.saturation"
    assert metrics[0].latest is not None
    assert len(await c.get_fixture_timeline()) == 7
    await c.close()  # default no-op


def test_factory_returns_mock_when_no_creds():
    c = build_observability_client(Settings(use_mocks=True))
    assert isinstance(c, MockMCPClient)


def test_factory_returns_live_when_configured():
    s = Settings(
        use_mocks=False,
        dt_tenant_url="https://x.live.dynatrace.com",
        dt_api_token="tok",
    )
    c = build_observability_client(s)
    assert isinstance(c, DynatraceMCPClient)
    assert c.mode == "live"


def test_map_severity_and_entity_type():
    assert DynatraceMCPClient.map_severity("ERROR") == Severity.HIGH
    assert DynatraceMCPClient.map_severity("AVAILABILITY") == Severity.CRITICAL
    assert DynatraceMCPClient.map_severity(None) == Severity.MEDIUM
    assert DynatraceMCPClient.map_severity("weird") == Severity.MEDIUM
    assert DynatraceMCPClient.map_entity_type("HOST") == EntityType.HOST
    assert DynatraceMCPClient.map_entity_type("DATABASE") == EntityType.DATABASE
    assert DynatraceMCPClient.map_entity_type(None) == EntityType.SERVICE


def test_parse_entity_variants():
    e = DynatraceMCPClient.parse_entity(
        {"entityId": "E1", "displayName": "svc", "type": "SERVICE",
         "tags": [{"key": "k"}, "plain"], "health": 80}
    )
    assert e.id == "E1" and e.name == "svc" and e.health == 80.0
    assert "k" in e.tags and "plain" in e.tags
    e2 = DynatraceMCPClient.parse_entity({})
    assert e2.id == "unknown" and e2.type == EntityType.SERVICE


def test_parse_problem_full_and_minimal():
    payload = {
        "problemId": "P1",
        "title": "boom",
        "severityLevel": "ERROR",
        "status": "OPEN",
        "startTime": 1700000000000,
        "affectedEntities": [{"entityId": "E", "displayName": "e", "type": "SERVICE"}],
        "rootCauseEntity": {
            "entityId": "DB",
            "name": "db",
            "type": "DATABASE",
            "confidence": 0.9,
            "contribution": "saturated",
        },
        "events": [
            {"eventId": "EV", "title": "t", "entityId": "E",
             "startTime": 1700000001000, "description": "d"}
        ],
    }
    p = DynatraceMCPClient.parse_problem(payload)
    assert p.id == "P1"
    assert p.severity == Severity.HIGH
    assert p.status == ProblemStatus.OPEN
    assert p.root_cause.entity_name == "db"
    assert p.events[0].title == "t"

    minimal = DynatraceMCPClient.parse_problem({})
    assert minimal.id == "unknown"
    assert minimal.root_cause is None
    assert minimal.status == ProblemStatus.OPEN


def test_parse_problem_resolved_with_endtime():
    p = DynatraceMCPClient.parse_problem(
        {"problemId": "P", "status": "RESOLVED", "endTime": 1700000005000,
         "events": [{}]}
    )
    assert p.status == ProblemStatus.RESOLVED
    assert p.resolved_at is not None
    # event with missing fields uses index-based id
    assert p.events[0].id == "EV-0"


def test_parse_metric():
    payload = {
        "result": [
            {
                "metricId": "m1",
                "data": [
                    {"timestamps": [1700000000000, 1700000001000],
                     "values": [1.0, None]}
                ],
            }
        ]
    }
    metrics = DynatraceMCPClient.parse_metric("E", payload)
    assert metrics[0].key == "m1"
    assert len(metrics[0].points) == 1  # None filtered out


async def _mock_transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler),
                             base_url="https://x.live.dynatrace.com")


async def test_live_calls_with_mock_transport():
    s = Settings(use_mocks=False, dt_tenant_url="https://x.live.dynatrace.com",
                 dt_api_token="t")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/problems":
            return httpx.Response(200, json={"problems": [
                {"problemId": "P1", "title": "x", "severityLevel": "ERROR",
                 "status": "OPEN", "startTime": 1700000000000}]})
        if request.url.path == "/api/v2/problems/P1":
            return httpx.Response(200, json={"problemId": "P1", "title": "x",
                                             "severityLevel": "ERROR",
                                             "status": "OPEN"})
        if request.url.path == "/api/v2/problems/MISSING":
            return httpx.Response(404)
        if request.url.path == "/api/v2/entities":
            return httpx.Response(200, json={"entities": [
                {"entityId": "E", "displayName": "svc", "type": "SERVICE"}]})
        if request.url.path == "/api/v2/metrics/query":
            return httpx.Response(200, json={"result": [
                {"metricId": "m", "data": [
                    {"timestamps": [1700000000000], "values": [5.0]}]}]})
        return httpx.Response(404)

    http = await _mock_transport(handler)
    client = DynatraceMCPClient(s, http)
    probs = await client.list_problems(open_only=True)
    assert probs[0].id == "P1"
    assert (await client.get_problem("P1")).id == "P1"
    assert await client.get_problem("MISSING") is None
    ents = await client.list_entities()
    assert ents[0].name == "svc"
    metrics = await client.get_metrics("E")
    assert metrics[0].points[0].value == 5.0
    assert len(await client.get_fixture_timeline()) == 7
    await client.close()


def test_create_classmethod_builds_client():
    s = Settings(use_mocks=False, dt_tenant_url="https://x.live.dynatrace.com/",
                 dt_api_token="tok")
    c = DynatraceMCPClient.create(s)
    assert isinstance(c, DynatraceMCPClient)
