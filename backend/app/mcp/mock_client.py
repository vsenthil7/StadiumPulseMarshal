"""Mock observability client — scenario-aware.

Backed by a selectable Scenario from the registry, so the mock can serve any of
the registered matchday situations (payment DB saturation, CDN edge, network
partition, k8s OOM). Defaults to the canonical payment scenario, preserving the
original demo while adding breadth.
"""
from __future__ import annotations

from datetime import timedelta

from app.fixtures.scenarios.registry import DEFAULT_SCENARIO, get_scenario
from app.mcp.base import ObservabilityClient
from app.models.domain import (
    Entity,
    FixtureTimelineEntry,
    Metric,
    MetricPoint,
    Problem,
)


class MockMCPClient(ObservabilityClient):
    """Returns deterministic data for a selected scenario."""

    def __init__(self, scenario_key: str = DEFAULT_SCENARIO) -> None:
        self._scenario_key = scenario_key
        self._scenario = get_scenario(scenario_key)

    @property
    def mode(self) -> str:
        return "mock"

    @property
    def scenario_key(self) -> str:
        return self._scenario_key

    def set_scenario(self, key: str) -> None:
        self._scenario_key = key
        self._scenario = get_scenario(key)

    async def list_problems(self, *, open_only: bool = False) -> list[Problem]:
        probs = self._scenario.problems
        if open_only:
            probs = [p for p in probs if p.is_open]
        return probs

    async def get_problem(self, problem_id: str) -> Problem | None:
        for p in self._scenario.problems:
            if p.id == problem_id:
                return p
        return None

    async def list_entities(self) -> list[Entity]:
        return self._scenario.entities

    async def get_metrics(self, entity_id: str) -> list[Metric]:
        base = self._scenario.match.kickoff + timedelta(minutes=40)
        for e in self._scenario.entities:
            if e.id == entity_id:
                sat = max(0.0, 100.0 - e.health)
                pts = [
                    MetricPoint(timestamp=base + timedelta(minutes=i),
                                value=round(sat * (0.6 + 0.1 * i), 2))
                    for i in range(6)
                ]
                return [Metric(key="entity.saturation", unit="%",
                               entity_id=entity_id, points=pts)]
        return [Metric(key="entity.saturation", unit="%", entity_id=entity_id,
                       points=[MetricPoint(timestamp=base, value=10.0)])]

    async def get_fixture_timeline(self) -> list[FixtureTimelineEntry]:
        return self._scenario.timeline
