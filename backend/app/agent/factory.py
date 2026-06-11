"""Factory selecting the reasoning agent based on settings."""
from __future__ import annotations

from app.agent.base import MockReasoningAgent, ReasoningAgent
from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


def build_agent(settings: Settings) -> ReasoningAgent:
    """Return the Gemini agent when configured, else the mock agent."""
    if settings.gemini_live:
        try:
            from app.agent.gemini_agent import GeminiReasoningAgent

            agent = GeminiReasoningAgent.create(settings)
            log.info("Using live Gemini reasoning agent")
            return agent
        except Exception as exc:  # pragma: no cover - depends on optional SDK
            log.warning("Gemini init failed (%s); falling back to mock", exc)
    log.warning("Gemini unavailable or mocks forced — using mock agent")
    return MockReasoningAgent()
