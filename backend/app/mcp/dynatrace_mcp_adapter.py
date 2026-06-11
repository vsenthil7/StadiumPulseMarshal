"""Dynatrace observability client over the MCP JSON-RPC protocol.

Where ``DynatraceMCPClient`` (dynatrace_client.py) uses the Environment API v2
directly, this adapter speaks the actual MCP protocol: it calls named Dynatrace
MCP tools (e.g. ``list_problems``, ``get_problem_details``) and maps the tool
results into the shared domain models. Both satisfy ``ObservabilityClient``.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.fixtures import matchday
from app.mcp.base import ObservabilityClient
from app.mcp.dynatrace_client import DynatraceMCPClient
from app.mcp.protocol import MCPSession
from app.models.domain import Entity, FixtureTimelineEntry, Metric, Problem

log = get_logger(__name__)

# Tool name mapping — overridable if the server names differ.
TOOL_LIST_PROBLEMS = "list_problems"
TOOL_GET_PROBLEM = "get_problem_details"
TOOL_LIST_ENTITIES = "list_entities"
TOOL_GET_METRICS = "get_metrics"


class DynatraceMCPProtocolClient(ObservabilityClient):
    """Observability client backed by a live MCP session."""

    def __init__(self, session: MCPSession) -> None:
        self._session = session

    @classmethod
    def create(cls, settings: Settings) -> "DynatraceMCPProtocolClient":
        headers = {}
        if settings.dt_api_token:
            headers["Authorization"] = f"Api-Token {settings.dt_api_token}"
        http = httpx.AsyncClient(headers=headers, timeout=20.0)
        session = MCPSession(settings.dt_mcp_url or "", http)
        return cls(session)

    @property
    def mode(self) -> str:
        return "live-mcp"

    async def _ensure_init(self) -> None:
        if not self._session.initialized:
            await self._session.initialize()

    @staticmethod
    def _as_list(result: Any, key: str) -> list[dict]:
        if isinstance(result, dict):
            return result.get(key, [])
        if isinstance(result, list):
            return result
        return []

    async def list_problems(self, *, open_only: bool = False) -> list[Problem]:
        await self._ensure_init()
        args = {"status": "OPEN"} if open_only else {}
        result = await self._session.call_tool(TOOL_LIST_PROBLEMS, args)
        return [
            DynatraceMCPClient.parse_problem(p)
            for p in self._as_list(result, "problems")
        ]

    async def get_problem(self, problem_id: str) -> Problem | None:
        await self._ensure_init()
        result = await self._session.call_tool(
            TOOL_GET_PROBLEM, {"problemId": problem_id}
        )
        if not result or (isinstance(result, dict) and not result):
            return None
        if isinstance(result, dict):
            return DynatraceMCPClient.parse_problem(result)
        return None

    async def list_entities(self) -> list[Entity]:
        await self._ensure_init()
        result = await self._session.call_tool(TOOL_LIST_ENTITIES, {})
        return [
            DynatraceMCPClient.parse_entity(e)
            for e in self._as_list(result, "entities")
        ]

    async def get_metrics(self, entity_id: str) -> list[Metric]:
        await self._ensure_init()
        result = await self._session.call_tool(
            TOOL_GET_METRICS, {"entityId": entity_id}
        )
        if isinstance(result, dict):
            return DynatraceMCPClient.parse_metric(entity_id, result)
        return []

    async def get_fixture_timeline(self) -> list[FixtureTimelineEntry]:
        # Match timeline comes from the tournament scheduling system.
        return matchday.fixture_timeline()

    async def close(self) -> None:  # pragma: no cover - thin shutdown
        await self._session._http.aclose()
