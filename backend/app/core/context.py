"""Application context: wires together settings, clients, agent and store."""
from __future__ import annotations

from app.agent.base import ReasoningAgent
from app.agent.factory import build_agent
from app.core.config import Settings, get_settings
from app.mcp.base import ObservabilityClient
from app.mcp.factory import build_observability_client
from app.services.store import RemediationStore


class AppContext:
    """Holds long-lived singletons for the application lifespan."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client: ObservabilityClient = build_observability_client(self.settings)
        self.agent: ReasoningAgent = build_agent(self.settings)
        self.store = RemediationStore(self.settings)

    async def shutdown(self) -> None:
        await self.client.close()
