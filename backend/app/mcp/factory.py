"""Factory that selects the observability client based on settings."""
from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger
from app.mcp.base import ObservabilityClient
from app.mcp.dynatrace_client import DynatraceMCPClient
from app.mcp.mock_client import MockMCPClient

log = get_logger(__name__)


def build_observability_client(settings: Settings) -> ObservabilityClient:
    """Choose the observability client.

    Priority when live: a full MCP JSON-RPC client if an MCP URL is configured,
    else the Dynatrace Environment API v2 client. Falls back to mock otherwise.
    """
    if settings.dynatrace_live:
        if settings.dt_mcp_url:
            from app.mcp.dynatrace_mcp_adapter import DynatraceMCPProtocolClient

            log.info("Using live Dynatrace MCP (JSON-RPC) client")
            return DynatraceMCPProtocolClient.create(settings)
        log.info("Using live Dynatrace Environment API client")
        return DynatraceMCPClient.create(settings)
    log.warning("Dynatrace credentials absent or mocks forced — using mock client")
    return MockMCPClient()
