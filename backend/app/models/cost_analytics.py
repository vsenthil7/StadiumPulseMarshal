"""Cost / capacity analytics — per-service spend + utilisation estimates."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ServiceCost(BaseModel):
    service_id: str
    service_name: str = ""
    monthly_cost_usd: float = 0.0
    cpu_utilisation: float = 0.0  # 0..1
    memory_utilisation: float = 0.0  # 0..1
    instance_count: int = 1
    venue_id: str | None = None
    # Simple right-sizing signal: low utilisation + cost = candidate to downsize.
    rightsizing: str = "ok"  # ok | downsize | upsize


class CostSummary(BaseModel):
    total_monthly_cost_usd: float = 0.0
    services: list[ServiceCost] = Field(default_factory=list)
    downsize_candidates: int = 0
    upsize_candidates: int = 0
