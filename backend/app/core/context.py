"""Application context: wires settings, clients, agent, repositories, services."""
from __future__ import annotations

from app.agent.base import ReasoningAgent
from app.agent.factory import build_agent
from app.core.config import Settings, get_settings
from app.fixtures.scenarios.registry import DEFAULT_SCENARIO
from app.mcp.base import ObservabilityClient
from app.mcp.factory import build_observability_client
from app.repositories.factory import RepositoryBundle, build_repositories
from app.services.analytics import AnalyticsSummary, compute_summary
from app.services.escalation_engine import EscalationEngine
from app.services.incident_service import IncidentService
from app.services.notification_service import NotificationService
from app.services.ops_defaults import (
    default_escalation_policies,
    default_on_call,
    synthetic_measurement,
)
from app.services.slo_engine import SLOEngine
from app.services.store import RemediationStore


class AppContext:
    """Holds long-lived singletons for the application lifespan."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client: ObservabilityClient = build_observability_client(self.settings)
        self.agent: ReasoningAgent = build_agent(self.settings)
        self.store = RemediationStore(self.settings)

        # Persistence + services.
        self.repos: RepositoryBundle = build_repositories(self.settings)
        self.notifications = NotificationService(self.repos.notifications)
        self.escalation = EscalationEngine(
            default_escalation_policies(), default_on_call()
        )
        # Event bus + webhook dispatcher.
        import httpx

        from app.events.bus import EventBus
        from app.services.webhook_service import (
            WebhookDispatcher,
            WebhookRepository,
        )

        self.events = EventBus()
        self.webhooks = WebhookRepository()
        self._webhook_http = httpx.AsyncClient()
        self.webhook_dispatcher = WebhookDispatcher(
            self.webhooks, self._webhook_http,
            timeout=self.settings.webhook_timeout_seconds,
        )
        self.webhook_dispatcher.register(self.events)

        self.incidents = IncidentService(
            self.repos.incidents, self.escalation, self.notifications,
            events=self.events,
        )
        self.slo_engine = SLOEngine(self._collect_slos())
        from app.services.slo_history import SLOHistory

        self.slo_history = SLOHistory()
        self.current_scenario = self._initial_scenario()

    def _initial_scenario(self) -> str:
        # Mock client exposes the scenario; live clients have none.
        return getattr(self.client, "scenario_key", DEFAULT_SCENARIO)

    def _collect_slos(self):
        # SLOs come from the active mock scenario when present.
        from app.fixtures.scenarios.registry import get_scenario

        key = getattr(self.client, "scenario_key", DEFAULT_SCENARIO)
        try:
            return get_scenario(key).slos
        except Exception:  # pragma: no cover - defensive
            return []

    def set_scenario(self, key: str) -> None:
        """Switch the active scenario (mock mode) and refresh SLOs."""
        if hasattr(self.client, "set_scenario"):
            self.client.set_scenario(key)  # type: ignore[attr-defined]
            self.current_scenario = key
            self.slo_engine = SLOEngine(self._collect_slos())

    async def evaluate_slos(self):
        """Compute current error budgets from synthetic/live measurements."""
        measurements = [synthetic_measurement(s) for s in self.slo_engine.slos]
        budgets = self.slo_engine.evaluate(measurements)
        for b in budgets:
            await self.repos.slo.save_budget(b)
        self.slo_history.record(budgets)
        return budgets

    async def analytics(self) -> AnalyticsSummary:
        incidents = await self.repos.incidents.list(limit=1000)
        budgets = await self.repos.slo.list_budgets()
        if not budgets:
            budgets = await self.evaluate_slos()
        return compute_summary(incidents, budgets)

    async def startup(self) -> None:
        await self.repos.init()

    async def shutdown(self) -> None:
        await self.client.close()
        await self.repos.dispose()
        await self._webhook_http.aclose()
