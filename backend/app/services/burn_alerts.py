"""Multi-window, multi-burn-rate SLO alerting (Google SRE workbook).

Classic burn-rate alerting fires when the error budget is being consumed fast
enough to matter, using *two* windows per tier so a brief spike doesn't page and
a real burn isn't missed:

  tier     long / short   burn-rate factor   budget burned   action
  ──────   ────────────   ────────────────   ─────────────   ──────
  fast     1h / 5m        14.4x              ~2% in 1h       PAGE
  medium   6h / 30m       6x                 ~5% in 6h       PAGE
  slow     24h / 2h       3x                 ~10% in 24h     TICKET
  trickle  72h / 6h       1x                 budget gone     TICKET

A tier fires only when BOTH its windows exceed the factor. We map the highest
firing tier to a severity (PAGE > TICKET > NONE).

In this build the observability source provides a current error rate per SLO; we
treat it as the rate in both windows (a single live sample), which is sufficient
to demonstrate the tiering. A real deployment would supply true per-window rates
from the metrics backend; the engine signature already accepts them.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.slo import SLO, BurnAlert, BurnSeverity, ErrorBudget


@dataclass(frozen=True)
class BurnTier:
    name: str
    long_hours: float
    short_hours: float
    factor: float
    severity: BurnSeverity


# Ordered most-urgent first.
BURN_TIERS: list[BurnTier] = [
    BurnTier("fast", 1.0, 5 / 60, 14.4, BurnSeverity.PAGE),
    BurnTier("medium", 6.0, 30 / 60, 6.0, BurnSeverity.PAGE),
    BurnTier("slow", 24.0, 2.0, 3.0, BurnSeverity.TICKET),
    BurnTier("trickle", 72.0, 6.0, 1.0, BurnSeverity.TICKET),
]


def _burn_rate(slo: SLO, error_rate: float) -> float:
    allowed = slo.allowed_error_fraction
    if allowed <= 0:
        return float("inf") if error_rate > 0 else 0.0
    return error_rate / allowed


def classify_burn(
    slo: SLO,
    long_error_rate: float,
    short_error_rate: float | None = None,
    venue_id: str | None = None,
) -> BurnAlert | None:
    """Return the highest-severity burn alert for an SLO, or None if silent.

    A tier fires only when BOTH windows' burn rate meet the factor. When a
    short-window rate isn't supplied we use the long-window rate for both.
    """
    short_error_rate = long_error_rate if short_error_rate is None else short_error_rate
    long_burn = _burn_rate(slo, long_error_rate)
    short_burn = _burn_rate(slo, short_error_rate)
    for tier in BURN_TIERS:
        if long_burn >= tier.factor and short_burn >= tier.factor:
            # Budget consumed per hour ≈ burn_rate * (1 / window_hours) * 100,
            # expressed against the SLO's full window for a readable percentage.
            consumed_pct = round(
                min(100.0, 100.0 * long_burn / max(1.0, slo.window_hours)), 2
            )
            return BurnAlert(
                slo_id=slo.id,
                slo_name=slo.name,
                service_id=slo.service_id,
                venue_id=venue_id,
                severity=tier.severity,
                burn_rate=round(long_burn, 3) if long_burn != float("inf") else 9999.0,
                long_window_hours=tier.long_hours,
                short_window_hours=tier.short_hours,
                factor=tier.factor,
                error_budget_consumed_pct=consumed_pct,
                message=(
                    f"{tier.name} burn: {slo.name} burning error budget at "
                    f"{long_burn:.1f}x (>= {tier.factor}x over "
                    f"{tier.long_hours:g}h/{tier.short_hours*60:g}m)"
                ),
            )
    return None


def evaluate_burn_alerts(
    slos: list[SLO],
    budgets: list[ErrorBudget],
    venue_of: dict[str, str | None] | None = None,
    metrics=None,
) -> list[BurnAlert]:
    """Build burn alerts from current budgets.

    If a ``metrics`` history is supplied, each tier is evaluated with the *real*
    long- and short-window error rates from recorded samples (the proper
    multi-window method). Without it (or when a window has no samples) we fall
    back to the budget's single ``achieved`` rate for both windows.
    """
    venue_of = venue_of or {}
    by_id = {s.id: s for s in slos}
    alerts: list[BurnAlert] = []
    for b in budgets:
        slo = by_id.get(b.slo_id)
        if slo is None:
            continue
        fallback_rate = max(0.0, 1.0 - b.achieved)
        venue = venue_of.get(b.slo_id)

        if metrics is not None and metrics.has_samples(b.slo_id):
            # Evaluate each tier with its own long/short windows; take the
            # highest-severity tier that fires on BOTH its windows.
            alert = _evaluate_with_windows(slo, b.slo_id, metrics, fallback_rate, venue)
        else:
            alert = classify_burn(slo, fallback_rate, venue_id=venue)
        if alert is not None:
            alerts.append(alert)
    return alerts


def _evaluate_with_windows(slo, slo_id, metrics, fallback_rate, venue):
    """Find the highest-severity tier whose long AND short window both exceed
    its burn factor, using real recorded per-window error rates."""
    for tier in BURN_TIERS:
        long_rate = metrics.error_rate_over(slo_id, tier.long_hours)
        short_rate = metrics.error_rate_over(slo_id, tier.short_hours)
        if long_rate is None:
            long_rate = fallback_rate
        if short_rate is None:
            short_rate = fallback_rate
        long_burn = _burn_rate(slo, long_rate)
        short_burn = _burn_rate(slo, short_rate)
        if long_burn >= tier.factor and short_burn >= tier.factor:
            consumed_pct = round(
                min(100.0, 100.0 * long_burn / max(1.0, slo.window_hours)), 2
            )
            return BurnAlert(
                slo_id=slo.id, slo_name=slo.name, service_id=slo.service_id,
                venue_id=venue, severity=tier.severity,
                burn_rate=round(long_burn, 3) if long_burn != float("inf") else 9999.0,
                long_window_hours=tier.long_hours,
                short_window_hours=tier.short_hours, factor=tier.factor,
                error_budget_consumed_pct=consumed_pct,
                message=(
                    f"{tier.name} burn: {slo.name} burning error budget at "
                    f"{long_burn:.1f}x (>= {tier.factor}x over "
                    f"{tier.long_hours:g}h/{tier.short_hours*60:g}m)"
                ),
            )
    return None
