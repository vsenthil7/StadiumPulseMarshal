"""SLO catalog: CRUD-ish read for SLO definitions + error-budget burn policy."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.auth import require_permission
from app.models.slo import SLO
from app.rbac.policy import Permission, Principal

router = APIRouter(prefix="/api/v1/slo-catalog", tags=["slo-catalog"])


def _engine(request: Request):
    return request.app.state.ctx.slo_engine


@router.get("", response_model=list[SLO])
async def list_slo_definitions(
    request: Request, service_id: str | None = None,
    _p: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> list[SLO]:
    slos = _engine(request).slos
    if service_id:
        slos = [s for s in slos if s.service_id == service_id]
    return slos


@router.get("/{slo_id}", response_model=SLO)
async def get_slo_definition(
    slo_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> SLO:
    slo = next((s for s in _engine(request).slos if s.id == slo_id), None)
    if slo is None:
        raise HTTPException(status_code=404, detail="SLO not found")
    return slo


@router.get("/{slo_id}/burn-policy")
async def get_burn_policy(
    slo_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> dict:
    """Return the burn-rate tier configuration for this SLO — which factors
    trigger PAGE vs TICKET, so operators can tune alert sensitivity."""
    from app.services.burn_alerts import BURN_TIERS

    slo = next((s for s in _engine(request).slos if s.id == slo_id), None)
    if slo is None:
        raise HTTPException(status_code=404, detail="SLO not found")
    tiers = [
        {
            "name": t.name,
            "long_hours": t.long_hours,
            "short_hours": t.short_hours,
            "factor": t.factor,
            "severity": t.severity.value,
            "allowed_error_rate": slo.allowed_error_fraction,
            "trigger_error_rate": round(slo.allowed_error_fraction * t.factor, 6),
        }
        for t in BURN_TIERS
    ]
    return {
        "slo_id": slo_id, "slo_name": slo.name, "target": slo.target,
        "window_hours": slo.window_hours,
        "allowed_error_fraction": slo.allowed_error_fraction,
        "burn_tiers": tiers,
    }
