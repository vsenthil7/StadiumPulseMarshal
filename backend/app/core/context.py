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
    default_oncall_pools,
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
        from app.services.oncall_directory import OnCallDirectory

        self.oncall_directory = OnCallDirectory(default_on_call())
        self.notifications.set_oncall_directory(self.oncall_directory)
        from app.services.kv_backend import build_kv

        self.kv = build_kv(self.settings.redis_url)
        from app.services.hash_burn_ack_store import HashBurnAckStore

        if getattr(self.repos, "database", None) is not None:
            from app.services.sql_burn_ack_store import SqlBurnAckStore

            self.burn_acks = SqlBurnAckStore(
                self.repos.database,
                ack_ttl_seconds=self.settings.burn_ack_ttl_seconds,
            )
        else:
            self.burn_acks = HashBurnAckStore(
                self.kv, ack_ttl_seconds=self.settings.burn_ack_ttl_seconds,
            )
        from app.services.burn_counters import BurnCounters

        self.burn_counters = BurnCounters(self.kv)
        from app.services.digest_mute_store import DigestMuteStore

        self.digest_mutes = DigestMuteStore(self.kv)
        self.digest_scheduler = None
        self.daily_digest_scheduler = None
        self.venue_fanout_scheduler = None
        from app.services.schedule_source import build_schedule_source

        self.schedule_source = build_schedule_source(
            self.settings, default_on_call(), pools=default_oncall_pools(),
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
        from app.services.metrics_history import MetricsHistory

        self.metrics_history = MetricsHistory()
        from app.services.metrics_source import build_metrics_source

        self.metrics_source = build_metrics_source(self.settings)
        self._metrics_backfilled = False
        from app.services.entity_venue import EntityVenueResolver

        self.entity_venue = EntityVenueResolver()
        from app.services.refresh_store import RefreshStore

        self.refresh_tokens = RefreshStore(repo=self.repos.refresh_tokens)
        from app.services.prune_scheduler import PruneScheduler

        self.prune_scheduler = PruneScheduler(
            self.refresh_tokens.prune,
            interval_seconds=self.settings.refresh_prune_interval_seconds,
        )
        from app.services.rate_limiter import RateLimiter

        self.auth_limiter = RateLimiter(
            self.settings.auth_rate_limit_per_minute, kv=self.kv
        )
        self.current_scenario = self._initial_scenario()

    async def refresh_oncall(self) -> None:
        """Refresh the on-call directory from the schedule source (current
        shift). Best-effort — failures leave the existing roster in place."""
        try:
            roster = await self.schedule_source.current_roster()
            if roster:
                self.oncall_directory.set_roster(roster)
        except Exception:  # pragma: no cover - defensive
            pass

    async def ensure_metrics_backfill(self) -> None:
        """Prime MetricsHistory with a real per-window error series from the
        configured metrics source (synthetic in mock mode, Dynatrace when
        configured). Idempotent — runs once unless the scenario changes."""
        if self._metrics_backfilled:
            return
        from app.services.metrics_source import backfill_history

        try:
            await backfill_history(
                self.metrics_source, self.slo_engine.slos, self.metrics_history,
            )
            self._metrics_backfilled = True
        except Exception:  # pragma: no cover - defensive
            pass

    async def ensure_entity_venue_map(self) -> None:
        """Populate the entity→venue resolver lazily from the active client.

        The zone→venue map comes from a ``ZoneSource`` — live Dynatrace
        management zones when a tenant is configured, else static config."""
        if not self.entity_venue.loaded:
            from app.services.zone_source import build_zone_source

            try:
                zone_mapping = await build_zone_source(self.settings).zone_to_venue()
            except Exception:  # pragma: no cover - defensive
                zone_mapping = self.settings.venue_zone_mapping
            try:
                entities = await self.client.list_entities()
                self.entity_venue.load(
                    entities,
                    zone_mapping=zone_mapping,
                    zone_tag_key=self.settings.venue_zone_tag_key,
                )
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
            self._metrics_backfilled = False

    async def evaluate_slos(self):
        """Compute current error budgets from synthetic/live measurements."""
        measurements = [synthetic_measurement(s) for s in self.slo_engine.slos]
        budgets = self.slo_engine.evaluate(measurements)
        for b in budgets:
            await self.repos.slo.save_budget(b)
        self.slo_history.record(budgets)
        # Record per-SLO error-rate samples for multi-window burn computation.
        for b in budgets:
            self.metrics_history.record(b.slo_id, max(0.0, 1.0 - b.achieved))
        return budgets

    async def analytics(
        self, principal_venues: list[str] | None = None,
        venue_filter: str | None = None,
        suppression_window_hours: float = 24.0,
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
        summary = compute_summary(incidents, budgets)
        # Surface multi-window burn-rate alert counts (scoped).
        try:
            from app.services.burn_alerts import evaluate_burn_alerts

            slo_entity = {s.id: s.service_id for s in self.slo_engine.slos}
            venue_of = {
                sid: self.entity_venue.venue_for(eid)
                for sid, eid in slo_entity.items()
            }
            alerts = evaluate_burn_alerts(self.slo_engine.slos, budgets, venue_of, metrics=self.metrics_history)
            if allowed is not None:
                alerts = [a for a in alerts
                          if a.venue_id is None or a.venue_id in allowed]
            summary.burn_page_alerts = sum(
                1 for a in alerts if a.severity.value == "page"
            )
            summary.burn_ticket_alerts = sum(
                1 for a in alerts if a.severity.value == "ticket"
            )
            # Suppression KPIs from the ack store + recent audit trail.
            active = await self.burn_acks.active_summary()
            summary.burn_active_acks = len(active["acks"])
            summary.burn_active_silences = len(active["silences"])
            from datetime import datetime, timezone

            audit = await self.audit.query(resource_type="burn_alert", limit=10_000)
            cutoff = datetime.now(timezone.utc).timestamp() - suppression_window_hours * 3600
            n_ack = n_sil = 0
            for e in audit:
                if e.at.timestamp() < cutoff:
                    continue
                if e.action == "burn.ack":
                    n_ack += 1
                elif e.action == "burn.silence":
                    n_sil += 1
            denom = n_ack + n_sil
            summary.burn_suppression_ratio = round(n_sil / denom, 3) if denom else 0.0
        except Exception:  # noqa: BLE001 - analytics must not fail on alerting
            pass
        return summary

    async def burn_alerts(
        self, principal_venues: list[str] | None = None, notify: bool = False,
    ) -> list:
        """Evaluate multi-window burn-rate alerts, scoped to the principal's
        venues (None = all). Maps each SLO to its owning venue for labels and
        scope."""
        from app.services.burn_alerts import evaluate_burn_alerts

        await self.ensure_entity_venue_map()
        await self.ensure_metrics_backfill()
        await self.refresh_oncall()
        budgets = await self.repos.slo.list_budgets()
        if not budgets:
            budgets = await self.evaluate_slos()
        slo_entity = {s.id: s.service_id for s in self.slo_engine.slos}
        venue_of = {
            sid: self.entity_venue.venue_for(eid)
            for sid, eid in slo_entity.items()
        }
        alerts = evaluate_burn_alerts(self.slo_engine.slos, budgets, venue_of, metrics=self.metrics_history)
        if principal_venues is not None:
            allowed = set(principal_venues)
            alerts = [
                a for a in alerts
                if a.venue_id is None or a.venue_id in allowed
            ]
        # Attach resolved on-call targets so callers (and the UI) can show who
        # a given burn alert would page, before/without dispatch.
        for a in alerts:
            sev = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
            a.on_call_targets = [
                {"name": t.name, "tier": t.tier.value, "recipient": t.recipient,
                 "channels": [c.value for c in t.channels]}
                for t in self.oncall_directory.targets_for_severity(sev)
            ]
            # Acknowledge / silence state.
            ack = await self.burn_acks.ack_for(a.slo_id, sev)
            if ack is not None:
                a.acknowledged = True
                a.acked_by = ack.acked_by
            a.silenced = await self.burn_acks.is_silenced(a.slo_id, sev)
        # Auto-route page/ticket burn alerts to notification channels (the
        # service dedupes per slo+severity within the alert window). Silenced
        # alerts are not dispatched.
        if notify:
            for a in alerts:
                if a.silenced:
                    continue
                try:
                    await self.notifications.notify_burn_alert(a)
                except Exception:  # noqa: BLE001 - alerting must not fail reads
                    pass
        return alerts

    async def analytics_by_venue(
        self, principal_venues: list[str] | None = None,
    ) -> list:
        """Per-venue rollups, scoped to the principal's venues (None = all).

        Determines the set of venues to report, maps each SLO budget to its
        owning venue via the entity resolver, and computes per-venue metrics.
        """
        from app.services.analytics import compute_by_venue

        await self.ensure_entity_venue_map()
        incidents = await self.repos.incidents.list(limit=1000)
        budgets = await self.repos.slo.list_budgets()
        if not budgets:
            budgets = await self.evaluate_slos()

        slo_entity = {s.id: s.service_id for s in self.slo_engine.slos}
        budgets_by_venue: dict[str, list] = {}
        for b in budgets:
            v = self.entity_venue.venue_for(slo_entity.get(b.slo_id))
            if v:
                budgets_by_venue.setdefault(v, []).append(b)

        # Venue universe: those appearing on incidents or SLOs (plus known
        # demo venues), then intersected with the principal's scope.
        seen = {i.venue_id for i in incidents if i.venue_id}
        seen |= set(budgets_by_venue.keys())
        if principal_venues is not None:
            seen &= set(principal_venues)
        venues = sorted(seen)
        if principal_venues is not None:
            incidents = [
                i for i in incidents
                if i.venue_id is None or i.venue_id in set(principal_venues)
            ]
        return compute_by_venue(incidents, budgets_by_venue, venues)

    async def startup(self) -> None:
        from app.core.config import ConfigurationError

        problems = self.settings.validate_for_startup()
        if problems:
            raise ConfigurationError("; ".join(problems))
        await self.repos.init()
        self.relay.start()
        self.prune_scheduler.start()
        if self.settings.burn_digest_enabled:
            from app.services.digest_service import DigestScheduler
            from app.models.notification import NotificationChannel

            ch = NotificationChannel(self.settings.burn_digest_channel) \
                if self.settings.burn_digest_channel in {c.value for c in NotificationChannel} \
                else NotificationChannel.SLACK

            async def _dispatch_digest(msg: str) -> None:
                await self.notifications.notify_digest(
                    msg, channel=ch, recipient=self.settings.burn_digest_recipient,
                    webhook_url=self.settings.burn_digest_webhook_url,
                    webhook_poster=self.webhook_dispatcher.post_message)

            self.digest_scheduler = DigestScheduler(
                self, self.settings.burn_digest_interval_seconds,
                dispatch=_dispatch_digest,
                window_hours=self.settings.burn_digest_window_hours,
                min_severity=self.settings.burn_digest_min_severity,
            )
            self.digest_scheduler.start()
        if self.settings.burn_daily_digest_enabled:
            from app.services.digest_service import (
                DailyAtScheduler, compose_daily_digest)
            from app.models.notification import NotificationChannel

            dch = NotificationChannel(self.settings.burn_daily_digest_channel) \
                if self.settings.burn_daily_digest_channel in {c.value for c in NotificationChannel} \
                else NotificationChannel.SLACK

            async def _dispatch_daily(msg: str) -> None:
                await self.notifications.notify_digest(
                    msg, channel=dch,
                    recipient=self.settings.burn_daily_digest_recipient,
                    webhook_url=self.settings.burn_digest_webhook_url,
                    webhook_poster=self.webhook_dispatcher.post_message)

            self.daily_digest_scheduler = DailyAtScheduler(
                self, self.settings.burn_daily_digest_at,
                composer=compose_daily_digest, dispatch=_dispatch_daily,
                tz=self.settings.burn_daily_digest_tz)
            self.daily_digest_scheduler.start()
        if self.settings.burn_digest_venue_fanout_enabled \
                and self.settings.burn_digest_venue_channel_map:
            from app.services.digest_service import VenueFanoutScheduler
            from app.models.notification import NotificationChannel

            fch = NotificationChannel(self.settings.burn_digest_channel) \
                if self.settings.burn_digest_channel in {c.value for c in NotificationChannel} \
                else NotificationChannel.SLACK

            async def _dispatch_venue(venue_id: str, recipient: str, msg: str) -> None:
                await self.notifications.notify_digest(
                    msg, channel=fch, recipient=recipient,
                    webhook_url=self.settings.burn_digest_webhook_url,
                    webhook_poster=self.webhook_dispatcher.post_message)

            self.venue_fanout_scheduler = VenueFanoutScheduler(
                self, self.settings.burn_digest_venue_fanout_interval_seconds,
                self.settings.burn_digest_venue_channel_map,
                dispatch=_dispatch_venue, mute_store=self.digest_mutes)
            self.venue_fanout_scheduler.start()

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
        await self.prune_scheduler.stop()
        if getattr(self, "digest_scheduler", None) is not None:
            await self.digest_scheduler.stop()
        if getattr(self, "daily_digest_scheduler", None) is not None:
            await self.daily_digest_scheduler.stop()
        if getattr(self, "venue_fanout_scheduler", None) is not None:
            await self.venue_fanout_scheduler.stop()
        await self.relay.stop()
        try:
            await self.kv.close()
        except Exception:  # noqa: BLE001
            pass
        await self.client.close()
        await self.repos.dispose()
        await self._webhook_http.aclose()
