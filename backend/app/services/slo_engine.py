"""SLO engine: computes error budgets and burn-rate classification.

Burn rate is expressed as the multiple of the budget-neutral consumption rate:
a burn rate of 1.0 exactly exhausts the budget over the SLO window; higher means
faster. We classify using common multi-window thresholds (Google SRE workbook
style, simplified to a single measured window here).
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.models.slo import BurnState, ErrorBudget, SLO, SLOMeasurement

log = get_logger(__name__)

# Burn-rate thresholds (multiples of budget-neutral rate).
FAST_BURN_THRESHOLD = 2.0
SLOW_BURN_THRESHOLD = 1.0


def compute_error_budget(slo: SLO, measurement: SLOMeasurement) -> ErrorBudget:
    """Compute the error-budget status for an SLO given a measurement.

    Two distinct quantities:

    * ``consumed_fraction`` — how much of the *cumulative* budget the observed
      error has used, scaled by how much of the full SLO window the observation
      covers. At/above 1.0 the budget is exhausted.
    * ``burn_rate`` — the *current* error rate divided by the budget-neutral
      error rate (= allowed error fraction). A burn rate of N means the budget
      would be exhausted in (window / N). This can be high while cumulative
      consumption is still low, which is exactly what fast/slow-burn alerts key
      on.
    """
    achieved = measurement.achieved
    allowed = slo.allowed_error_fraction
    observed_error = measurement.error_rate
    # Fraction of the full SLO window that this observation covers.
    window_fraction = min(
        1.0, measurement.observation_window_hours / slo.window_hours
    )

    if allowed <= 0:
        # A 100% target: any error exhausts the budget.
        consumed = 1.0 if observed_error > 0 else 0.0
        burn_rate = float("inf") if observed_error > 0 else 0.0
    else:
        burn_rate = observed_error / allowed
        # Budget consumed so far ≈ burn_rate * fraction-of-window-elapsed.
        consumed = burn_rate * window_fraction

    remaining = max(0.0, 1.0 - consumed)
    state = _classify(consumed, burn_rate)

    return ErrorBudget(
        slo_id=slo.id,
        slo_name=slo.name,
        target=slo.target,
        achieved=achieved,
        consumed_fraction=round(consumed, 6),
        remaining_fraction=round(remaining, 6),
        burn_rate=round(burn_rate, 4) if burn_rate != float("inf") else 9999.0,
        state=state,
    )


def _classify(consumed: float, burn_rate: float) -> BurnState:
    # A sustained fast burn is the most urgent signal — surface it even before
    # cumulative exhaustion. Then slow burn, then exhaustion of remaining budget.
    if burn_rate >= FAST_BURN_THRESHOLD:
        return BurnState.FAST_BURN
    if consumed >= 1.0:
        return BurnState.EXHAUSTED
    if burn_rate >= SLOW_BURN_THRESHOLD:
        return BurnState.SLOW_BURN
    return BurnState.HEALTHY


class SLOEngine:
    """Evaluates a set of SLOs against provided measurements."""

    def __init__(self, slos: list[SLO]) -> None:
        self._slos = {s.id: s for s in slos}

    @property
    def slos(self) -> list[SLO]:
        return list(self._slos.values())

    def get(self, slo_id: str) -> SLO | None:
        return self._slos.get(slo_id)

    def evaluate(self, measurements: list[SLOMeasurement]) -> list[ErrorBudget]:
        budgets: list[ErrorBudget] = []
        for m in measurements:
            slo = self._slos.get(m.slo_id)
            if slo is None:
                continue
            budgets.append(compute_error_budget(slo, m))
        return budgets

    def worst(self, budgets: list[ErrorBudget]) -> ErrorBudget | None:
        if not budgets:
            return None
        return max(budgets, key=lambda b: b.state.rank)
