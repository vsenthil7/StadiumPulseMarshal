"""API routes for StadiumPulse Marshal."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.auth import (
    require_permission,
    require_venue_access,
    scope_collection,
)
from app.api.schemas import (
    AnalyzeResponse,
    AuditResponse,
    ConfigResponse,
    DecisionRequest,
    DecisionResponse,
    EntityList,
    ExecuteResponse,
    HealthResponse,
    ProblemList,
    RemediationList,
    SettingsUpdate,
    TimelineResponse,
)
from app.core.context import AppContext
from app.models.domain import Problem
from app.rbac.policy import Permission, Principal

router = APIRouter(prefix="/api/v1")


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/config", response_model=ConfigResponse, tags=["system"])
async def config(request: Request) -> ConfigResponse:
    ctx = _ctx(request)
    s = ctx.settings
    return ConfigResponse(
        app_name=s.app_name,
        app_version=s.app_version,
        data_source=s.data_source,
        dynatrace_live=s.dynatrace_live,
        gemini_live=s.gemini_live,
        agent_backend=ctx.agent.backend,
        auto_approve_low_risk=s.auto_approve_low_risk,
    )


@router.get("/problems", response_model=ProblemList, tags=["observability"])
async def list_problems(
    request: Request, open_only: bool = False, venue_id: str | None = None,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> ProblemList:
    ctx = _ctx(request)
    problems = await ctx.client.list_problems(open_only=open_only)
    problems = scope_collection(principal, problems, venue_id)
    return ProblemList(problems=problems)


@router.get(
    "/problems/{problem_id}",
    response_model=Problem,
    tags=["observability"],
)
async def get_problem(
    request: Request, problem_id: str,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> Problem:
    ctx = _ctx(request)
    problem = await ctx.client.get_problem(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    require_venue_access(principal, problem.venue_id)
    return problem


@router.get("/entities", response_model=EntityList, tags=["observability"])
async def list_entities(
    request: Request, venue_id: str | None = None,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> EntityList:
    ctx = _ctx(request)
    entities = await ctx.client.list_entities()
    entities = scope_collection(principal, entities, venue_id)
    return EntityList(entities=entities)


@router.get("/timeline", response_model=TimelineResponse, tags=["observability"])
async def timeline(request: Request) -> TimelineResponse:
    ctx = _ctx(request)
    return TimelineResponse(timeline=await ctx.client.get_fixture_timeline())


@router.post(
    "/agent/analyze/{problem_id}",
    response_model=AnalyzeResponse,
    tags=["agent"],
)
async def analyze(request: Request, problem_id: str) -> AnalyzeResponse:
    ctx = _ctx(request)
    problem = await ctx.client.get_problem(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    analysis = await ctx.agent.analyze(problem)
    ctx.store.register(analysis.recommended_actions)

    # Apply auto-approve guardrails.
    for action in analysis.recommended_actions:
        if ctx.store.can_auto_approve(action, problem.severity):
            ctx.store.decide(
                action.id,
                approved=True,
                decided_by="auto-guardrail",
                reason="Low-risk within severity ceiling",
                auto=True,
            )
    return AnalyzeResponse(analysis=analysis)


@router.get("/remediations", response_model=RemediationList, tags=["remediation"])
async def list_remediations(request: Request, pending: bool = False) -> RemediationList:
    ctx = _ctx(request)
    actions = ctx.store.pending() if pending else ctx.store.list_actions()
    return RemediationList(actions=actions)


@router.post(
    "/remediations/{action_id}/approve",
    response_model=DecisionResponse,
    tags=["remediation"],
)
async def approve(
    request: Request, action_id: str, body: DecisionRequest,
    _p=Depends(require_permission(Permission.REMEDIATION_APPROVE)),
) -> DecisionResponse:
    ctx = _ctx(request)
    decision = ctx.store.decide(
        action_id, approved=True, decided_by=body.decided_by, reason=body.reason
    )
    if decision is None:
        raise HTTPException(status_code=404, detail="Remediation not found")
    action = ctx.store.get(action_id)
    assert action is not None
    return DecisionResponse(decision=decision, action=action)


@router.post(
    "/remediations/{action_id}/reject",
    response_model=DecisionResponse,
    tags=["remediation"],
)
async def reject(
    request: Request, action_id: str, body: DecisionRequest,
    _p=Depends(require_permission(Permission.REMEDIATION_APPROVE)),
) -> DecisionResponse:
    ctx = _ctx(request)
    decision = ctx.store.decide(
        action_id, approved=False, decided_by=body.decided_by, reason=body.reason
    )
    if decision is None:
        raise HTTPException(status_code=404, detail="Remediation not found")
    action = ctx.store.get(action_id)
    assert action is not None
    return DecisionResponse(decision=decision, action=action)


@router.get("/audit", response_model=AuditResponse, tags=["remediation"])
async def audit(request: Request) -> AuditResponse:
    ctx = _ctx(request)
    return AuditResponse(decisions=ctx.store.audit_log())


@router.post(
    "/remediations/{action_id}/execute",
    response_model=ExecuteResponse,
    tags=["remediation"],
)
async def execute(
    request: Request, action_id: str,
    _p=Depends(require_permission(Permission.REMEDIATION_APPROVE)),
) -> ExecuteResponse:
    """Mark an approved remediation as executed (human-in-the-loop apply step).

    In live mode this is where an approved runbook would be dispatched to the
    automation backend; here it transitions state and is auditable.
    """
    ctx = _ctx(request)
    action = ctx.store.get(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Remediation not found")
    from app.models.enums import RemediationStatus

    if action.status not in (
        RemediationStatus.APPROVED,
        RemediationStatus.AUTO_APPROVED,
    ):
        raise HTTPException(
            status_code=409, detail="Remediation must be approved before execution"
        )
    ok = ctx.store.mark_executed(action_id, success=True)
    # Dispatch to the configured automation backend (Cloud Workflows / AWX /
    # webhook). No-op in mock/demo mode (dispatched=False, target=none).
    dispatch_result = None
    try:
        dispatch_result = await ctx.remediation_dispatcher.dispatch(
            action, actor=getattr(_p, "subject", "system"))
    except Exception:  # noqa: BLE001 - execution state stands even if dispatch errors
        dispatch_result = {"dispatched": False, "target": "none"}
    return ExecuteResponse(action=action, executed=ok, dispatch=dispatch_result)


@router.patch("/settings", response_model=ConfigResponse, tags=["system"])
async def update_settings(
    request: Request, body: SettingsUpdate,
    _p=Depends(require_permission(Permission.SETTINGS_WRITE)),
) -> ConfigResponse:
    """Update human-in-the-loop guardrails at runtime."""
    ctx = _ctx(request)
    if body.auto_approve_low_risk is not None:
        ctx.settings.auto_approve_low_risk = body.auto_approve_low_risk
    if body.max_auto_approve_severity is not None:
        ctx.settings.max_auto_approve_severity = body.max_auto_approve_severity
    s = ctx.settings
    return ConfigResponse(
        app_name=s.app_name,
        app_version=s.app_version,
        data_source=s.data_source,
        dynatrace_live=s.dynatrace_live,
        gemini_live=s.gemini_live,
        agent_backend=ctx.agent.backend,
        auto_approve_low_risk=s.auto_approve_low_risk,
    )
