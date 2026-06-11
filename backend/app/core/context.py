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
            events=self.events, outbox=self.repos.outbox,
            audit=None,  # set just below once audit service exists
        )
        from app.services.audit_service import AuditService
        from app.services.outbox_relay import OutboxRelay

        self.audit = AuditService(self.repos.audit_log)
        self.incidents._audit = self.audit  # inject now that it exists
        self.relay = OutboxRelay(self.repos.outbox, self.events)
        from app.services.idempotency import IdempotencyStore

        self.idempotency = IdempotencyStore()
        self.slo_engine = SLOEngine(self._collect_slos())
        from app.services.slo_history import SLOHistory

        self.slo_history = SLOHistory()
        from app.services.entity_venue import EntityVenueResolver

        self.entity_venue = EntityVenueResolver()
        from app.services.refresh_store import RefreshStore

        self.refresh_tokens = RefreshStore()
        self.current_scenario = self._initial_scenario()

    async def ensure_entity_venue_map(self) -> None:
        """Populate the entity→venue resolver lazily from the active client."""
        if not self.entity_venue.loaded:
            try:
                entities = await self.client.list_entities()
                self.entity_venue.load(entities)
            except Exception:  # pragma: no cover - defensive
                self.entity_venue.load([])

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
            self.entity_venue.invalidate()

    async def evaluate_slos(self):
        """Compute current error budgets from synthetic/live measurements."""
        measurements = [synthetic_measurement(s) for s in self.slo_engine.slos]
        budgets = self.slo_engine.evaluate(measurements)
        for b in budgets:
            await self.repos.slo.save_budget(b)
        self.slo_history.record(budgets)
        return budgets

    async def analytics(
        self, principal_venues: list[str] | None = None,
        venue_filter: str | None = None,
    ) -> AnalyticsSummary:
        """Compute analytics, optionally scoped to a venue or a principal's
        venues. ``principal_venues=None`` means cross-venue (no restriction)."""
        await self.ensure_entity_venue_map()
        incidents = await self.repos.incidents.list(limit=1000)
        budgets = await self.repos.slo.list_budgets()
        if not budgets:
            budgets = await self.evaluate_slos()

        # Determine the allowed venue set.
        allowed: set[str] | None
        if venue_filter is not None:
            allowed = {venue_filter}
        elif principal_venues is not None:
            allowed = set(principal_venues)
        else:
            allowed = None  # cross-venue

        if allowed is not None:
            incidents = [
                i for i in incidents
                if i.venue_id is None or i.venue_id in allowed
            ]
            slo_entity = {s.id: s.service_id for s in self.slo_engine.slos}
            def _bv(b):
                return self.entity_venue.venue_for(slo_entity.get(b.slo_id))
            budgets = [b for b in budgets if _bv(b) is None or _bv(b) in allowed]
        return compute_summary(incidents, budgets)

    async def startup(self) -> None:
        from app.core.config import ConfigurationError

        problems = self.settings.validate_for_startup()
        if problems:
            raise ConfigurationError("; ".join(problems))
        await self.repos.init()
        self.relay.start()

    async def probe_readiness(self) -> dict:
        """Actively probe dependencies for the readiness endpoint."""
        checks: dict[str, str] = {}
        try:
            await self.client.list_problems(open_only=True)
            checks["observability_client"] = f"ok ({self.client.mode})"
        except Exception as exc:  # pragma: no cover - defensive
            checks["observability_client"] = f"error: {exc}"
        try:
            await self.repos.incidents.count()
            checks["persistence"] = (
                "ok (sql)" if self.repos.database is not None else "ok (memory)"
            )
        except Exception as exc:  # pragma: no cover - defensive
            checks["persistence"] = f"error: {exc}"
        checks["agent"] = f"ok ({self.agent.backend})"
        return checks

    async def shutdown(self) -> None:
        await self.relay.stop()
        await self.client.close()
        await self.repos.dispose()
        await self._webhook_http.aclose()
