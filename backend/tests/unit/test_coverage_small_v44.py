"""Coverage for small pure-logic services: metrics_history, entity_venue,
cost_analytics_service."""
from __future__ import annotations

from app.models.domain import Entity, EntityType
from app.services.metrics_history import MetricsHistory
from app.services.entity_venue import EntityVenueResolver
from app.services.cost_analytics_service import CostAnalyticsService


# ── metrics_history ──
def test_metrics_history_window_and_absence():
    h = MetricsHistory()
    assert h.error_rate_over("slo-x", 1.0) is None  # no samples at all
    now = 1_000_000.0
    h.record("slo-x", 0.2, weight=1.0, at=now - 100)
    h.record("slo-x", 0.4, weight=3.0, at=now - 50)
    # weighted mean = (0.2*1 + 0.4*3)/4 = 0.35
    val = h.error_rate_over("slo-x", 1.0, now=now)
    assert abs(val - 0.35) < 1e-9
    # window that excludes all samples → None (den==0 branch)
    assert h.error_rate_over("slo-x", 0.0001, now=now + 10_000) is None
    assert h.has_samples("slo-x") is True
    assert h.has_samples("nope") is False
    assert h.sample_count("slo-x") == 2
    assert h.sample_count("nope") == 0


def test_metrics_history_clamps_negatives():
    h = MetricsHistory()
    h.record("s", -0.5, weight=-2.0, at=100.0)  # both clamped to 0
    # error_rate clamped to 0, weight clamped to 0 → den==0 → None
    assert h.error_rate_over("s", 1.0, now=100.0) is None


# ── entity_venue ──
def _ent(eid, venue=None, tags=None):
    return Entity(id=eid, name=eid, type=EntityType.SERVICE,
                  tags=tags or [], venue_id=venue)


def test_entity_venue_explicit_and_zone_tag():
    r = EntityVenueResolver()
    assert r.loaded is False
    r.load(
        [
            _ent("e1", venue="venue_a"),                       # explicit
            _ent("e2", tags=["mz:Arena North"]),               # via zone tag
            _ent("e3", tags=["mz:Unknown Zone"]),              # unmapped → dropped
            _ent("e4"),                                        # no venue → dropped
        ],
        zone_mapping={"Arena North": "venue_arena_north"},
    )
    assert r.loaded is True
    assert r.venue_for("e1") == "venue_a"
    assert r.venue_for("e2") == "venue_arena_north"
    assert r.venue_for("e3") is None
    assert r.venue_for("e4") is None
    assert r.venue_for(None) is None
    assert set(r.known_venues()) == {"venue_a", "venue_arena_north"}
    # venue_for_any returns the first resolvable
    assert r.venue_for_any(["e3", "e2", "e1"]) == "venue_arena_north"
    assert r.venue_for_any(["e3", "e4"]) is None
    # invalidate resets state
    r.invalidate()
    assert r.loaded is False
    assert r.venue_for("e1") is None


# ── cost_analytics_service ──
def test_cost_summary_totals_and_rightsizing():
    svc = CostAnalyticsService()
    summ = svc.summary()
    # 4 seeded services; total is their sum
    assert summ.total_monthly_cost_usd == 4200 + 3100 + 9800 + 1400
    # Ticketing (0.18/0.22) + Concessions (0.12/0.15) → downsize; Streaming (0.91) → upsize
    assert summ.downsize_candidates == 2
    assert summ.upsize_candidates == 1
    assert len(summ.services) == 4


def test_cost_summary_venue_filter_includes_estate_wide():
    svc = CostAnalyticsService()
    # all seed services have venue_id=None (estate-wide) → included under any filter
    summ = svc.summary(venue_id="venue_arena_north")
    assert len(summ.services) == 4

