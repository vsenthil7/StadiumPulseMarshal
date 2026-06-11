"""Mock observability client backed by matchday fixtures."""
from __future__ import annotations

from app.fixtures import matchday
from app.mcp.base import ObservabilityClient
from app.models.domain import Entity, FixtureTimelineEntry, Metric, Problem


class MockMCPClient(ObservabilityClient):
    """Returns deterministic matchday scenario data."""

    @property
    def mode(self) -> str:
        return "mock"

    async def list_problems(self, *, open_only: bool = False) -> list[Problem]:
        probs = matchday.problems()
        if open_only:
            probs = [p for p in probs if p.is_open]
        return probs

    async def get_problem(self, problem_id: str) -> Problem | None:
        for p in matchday.problems():
            if p.id == problem_id:
                return p
        return None

    async def list_entities(self) -> list[Entity]:
        return matchday.entities()

    async def get_metrics(self, entity_id: str) -> list[Metric]:
        return matchday.metrics_for(entity_id)

    async def get_fixture_timeline(self) -> list[FixtureTimelineEntry]:
        return matchday.fixture_timeline()
