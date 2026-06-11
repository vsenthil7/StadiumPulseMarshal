"""Factory that selects the observability client based on settings."""
from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger
from app.mcp.base import ObservabilityClient
from app.mcp.dynatrace_client import DynatraceMCPClient
from app.mcp.mock_client import MockMCPClient

log = get_logger(__name__)


def build_observability_client(settings: Settings) -> ObservabilityClient:
    """Return a live Dynatrace client if configured, else the mock client."""
    if settings.dynatrace_live:
        log.info("Using live Dynatrace MCP client")
        return DynatraceMCPClient.create(settings)
    log.warning("Dynatrace credentials absent or mocks forced — using mock client")
    return MockMCPClient()
