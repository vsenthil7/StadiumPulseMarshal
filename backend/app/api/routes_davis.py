"""Davis AI feedback loop API: analysis read + outcome feedback + ranking."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.auth import require_permission
from app.rbac.policy import Permission, Principal

router = APIRouter(prefix="/api/v1/davis", tags=["davis-ai"])


def _ctx(request: Request):
    return request.app.state.ctx


@router.get("/problems/{problem_id}/analysis")
async def davis_problem_analysis(
    problem_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> dict:
    """Davis AI root-cause analysis. Delegates to the Dynatrace client when it
    exposes get_davis_analysis(), else returns a synthetic analysis."""
    client = _ctx(request).client
    if hasattr(client, "get_davis_analysis"):
        return await client.get_davis_analysis(problem_id)
    return {
        "problem_id": problem_id,
        "root_cause_entity": {"entityId": "SERVICE-mock", "name": "payment-service"},
        "evidence_details": {"evidences": [{"displayName": "Response time degradation"}]},
        "impact_analysis": {"estimatedAffectedUsers": 1200},
        "affected_entities": [],
        "source": "mock",
    }


class FeedbackBody(BaseModel):
    problem_id: str
    correct: bool
    notes: str = ""


@router.post("/feedback")
async def record_feedback(
    body: FeedbackBody, request: Request,
    principal: Principal = Depends(require_permission(Permission.REMEDIATION_APPROVE)),
) -> dict:
    """Record SRE outcome feedback on a Davis problem; updates its rank."""
    return await _ctx(request).davis.record_feedback(
        body.problem_id, body.correct, principal.subject, body.notes)


@router.get("/problems/{problem_id}/feedback")
async def get_feedback(
    problem_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> dict:
    svc = _ctx(request).davis
    return {"problem_id": problem_id, "rank": svc.rank(problem_id),
            "feedback": svc.feedback_for(problem_id)}


@router.get("/ranked")
async def ranked_problems(
    request: Request,
    _p: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> dict:
    return {"problems": _ctx(request).davis.ranked_problems()}
