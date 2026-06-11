"""Service-level objective domain models.

Models SLIs, SLOs and error budgets for matchday-critical services. The SLO
engine (services/slo_engine.py) computes burn rates and budget consumption from
these definitions plus live/mock measurements.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SLIKind(str, Enum):
    """The kind of service-level indicator."""

    AVAILABILITY = "AVAILABILITY"
    LATENCY = "LATENCY"
    ERROR_RATE = "ERROR_RATE"
    THROUGHPUT = "THROUGHPUT"
    SATURATION = "SATURATION"


class BurnState(str, Enum):
    """Error-budget burn classification."""

    HEALTHY = "HEALTHY"
    SLOW_BURN = "SLOW_BURN"
    FAST_BURN = "FAST_BURN"
    EXHAUSTED = "EXHAUSTED"

    @property
    def rank(self) -> int:
        # Ordered by operational urgency for 'worst-of' selection.
        return {
            "HEALTHY": 0,
            "SLOW_BURN": 1,
            "EXHAUSTED": 2,
            "FAST_BURN": 3,
        }[self.value]


class SLI(BaseModel):
    """A service-level indicator definition."""

    key: str
    kind: SLIKind
    entity_id: str
    unit: str = ""
    # For latency/error: 'good' events are those below/under threshold.
    threshold: float | None = None
    description: str = ""


class SLO(BaseModel):
    """A service-level objective: a target over a rolling window."""

    id: str
    name: str
    service_id: str
    sli: SLI
    # Target as a fraction, e.g. 0.999 for 99.9%.
    target: float = Field(ge=0.0, le=1.0)
    window_hours: int = Field(default=24, gt=0)
    description: str = ""

    @property
    def allowed_error_fraction(self) -> float:
        """The fraction of bad events the budget permits."""
        return 1.0 - self.target


class SLOMeasurement(BaseModel):
    """An observed good/total count for an SLO over an observation window.

    ``observation_window_hours`` is the length of the window these counts cover.
    Burn rate compares the error rate in this (typically short) window against
    the budget-neutral rate over the full SLO window, so it can read high (a fast
    burn) even when cumulative budget consumed-to-date is still under 100%.
    """

    slo_id: str
    good_events: int = Field(ge=0)
    total_events: int = Field(ge=0)
    observation_window_hours: float = Field(default=1.0, gt=0)
    measured_at: datetime = Field(default_factory=_utcnow)

    @property
    def achieved(self) -> float:
        if self.total_events == 0:
            return 1.0
        return self.good_events / self.total_events

    @property
    def bad_events(self) -> int:
        return self.total_events - self.good_events

    @property
    def error_rate(self) -> float:
        if self.total_events == 0:
            return 0.0
        return self.bad_events / self.total_events


class ErrorBudget(BaseModel):
    """Computed error-budget status for an SLO."""

    slo_id: str
    slo_name: str
    target: float
    achieved: float
    # Budget consumed as a fraction of the allowed error budget (0..>1).
    consumed_fraction: float
    remaining_fraction: float
    burn_rate: float
    state: BurnState
    computed_at: datetime = Field(default_factory=_utcnow)

    @property
    def is_breaching(self) -> bool:
        return self.achieved < self.target


class BurnSeverity(str, Enum):
    """Burn-rate alert severity, mapped to a response channel."""

    PAGE = "page"      # fast burn — wake someone now
    TICKET = "ticket"  # slow burn — file for the next working day
    NONE = "none"


class BurnAlert(BaseModel):
    """A multi-window burn-rate alert for one SLO.

    Fires only when BOTH the long and short windows exceed the tier's burn-rate
    factor (the standard Google SRE multi-window/multi-burn-rate guard against
    flapping). ``budget_consumed_pct_per_hour`` is a human-friendly read-out.
    """

    slo_id: str
    slo_name: str
    service_id: str
    venue_id: str | None = None
    severity: BurnSeverity
    burn_rate: float
    long_window_hours: float
    short_window_hours: float
    factor: float
    error_budget_consumed_pct: float
    message: str = ""
    on_call_targets: list[dict] = Field(default_factory=list)
    at: datetime = Field(default_factory=_utcnow)


class BurnAlertList(BaseModel):
    alerts: list[BurnAlert] = Field(default_factory=list)
    page_count: int = 0
    ticket_count: int = 0
