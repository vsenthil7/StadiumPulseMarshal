"""Abstract observability client interface.

Both the mock and the real Dynatrace MCP client implement this protocol, so the
rest of the application is agnostic to the data source.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.domain import Entity, FixtureTimelineEntry, Metric, Problem


class ObservabilityClient(ABC):
    """Common interface for retrieving observability data."""

    @property
    @abstractmethod
    def mode(self) -> str:
        """Return 'mock' or 'live'."""

    @abstractmethod
    async def list_problems(self, *, open_only: bool = False) -> list[Problem]:
        ...

    @abstractmethod
    async def get_problem(self, problem_id: str) -> Problem | None:
        ...

    @abstractmethod
    async def list_entities(self) -> list[Entity]:
        ...

    @abstractmethod
    async def get_metrics(self, entity_id: str) -> list[Metric]:
        ...

    @abstractmethod
    async def get_fixture_timeline(self) -> list[FixtureTimelineEntry]:
        ...

    async def close(self) -> None:  # pragma: no cover - default no-op
        """Release any resources (overridden by live client)."""
        return None
