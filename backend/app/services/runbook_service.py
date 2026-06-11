"""Runbook library CRUD and execution service (in-memory, seeded)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.models.runbook import Runbook, RunbookCategory, RunbookExecution

log = get_logger(__name__)


def _id() -> str:
    return f"RB-{uuid.uuid4().hex[:8]}"


def _eid() -> str:
    return f"RBE-{uuid.uuid4().hex[:8]}"


_SEED: list[dict] = [
    {
        "id": "RB-db-pool-scale",
        "name": "Database Connection Pool Scale-Up",
        "category": "database",
        "version": 1,
        "description": "Scale up connection pool ceiling during matchday surges.",
        "tags": ["database", "matchday", "capacity"],
        "owner": "sre-platform",
        "steps": [
            {"order": 1, "title": "Confirm pool saturation",
             "description": "Check db.connections.active == max in Dynatrace.",
             "verification": "db.connections.active shows 100%"},
            {"order": 2, "title": "Apply connection pool increase",
             "description": "Raise max_connections 2x via Cloud Workflows.",
             "automation_ref": "wf-db-pool-scale",
             "command": "gcloud workflows run db-pool-scale --data='{\"factor\":2}'",
             "verification": "db.connections.active drops below 80%",
             "rollback": "gcloud workflows run db-pool-scale --data='{\"factor\":0.5}'"},
        ],
    },
    {
        "id": "RB-svc-scaleout",
        "name": "Horizontal Service Scale-Out",
        "category": "scaling",
        "version": 1,
        "description": "Add Cloud Run instances during load spike.",
        "tags": ["scale", "cloud-run", "matchday"],
        "owner": "sre-platform",
        "steps": [
            {"order": 1, "title": "Identify saturated service",
             "description": "Confirm service CPU > 80% in Dynatrace.",
             "verification": "Dynatrace chart shows CPU spike"},
            {"order": 2, "title": "Increase Cloud Run max instances",
             "description": "Update max instances to 20.",
             "command": "gcloud run services update <SERVICE> --max-instances=20",
             "verification": "New instances reported healthy"},
        ],
    },
]


class RunbookService:
    def __init__(self, dispatcher=None) -> None:
        self._runbooks: dict[str, Runbook] = {
            r["id"]: Runbook(**r) for r in _SEED
        }
        self._executions: dict[str, RunbookExecution] = {}
        self._dispatcher = dispatcher

    def list_runbooks(self, category: RunbookCategory | None = None,
                      tag: str | None = None,
                      venue_id: str | None = None) -> list[Runbook]:
        results = list(self._runbooks.values())
        if category:
            results = [r for r in results if r.category == category]
        if tag:
            results = [r for r in results if tag in r.tags]
        if venue_id:
            results = [r for r in results
                       if not r.venue_ids or venue_id in r.venue_ids]
        return sorted(results, key=lambda r: r.name)

    def get_runbook(self, runbook_id: str) -> Runbook | None:
        return self._runbooks.get(runbook_id)

    def create_runbook(self, runbook: Runbook) -> Runbook:
        if not runbook.id:
            runbook = runbook.model_copy(update={"id": _id()})
        self._runbooks[runbook.id] = runbook
        log.info("Runbook created: %s (%s)", runbook.id, runbook.name)
        return runbook

    def update_runbook(self, runbook_id: str, patch: dict) -> Runbook | None:
        rb = self._runbooks.get(runbook_id)
        if rb is None:
            return None
        updated = rb.model_copy(update={
            **patch,
            "version": rb.version + 1,
            "updated_at": datetime.now(timezone.utc),
        })
        self._runbooks[runbook_id] = updated
        return updated

    def delete_runbook(self, runbook_id: str) -> bool:
        return self._runbooks.pop(runbook_id, None) is not None

    async def execute_runbook(self, runbook_id: str, actor: str,
                              incident_id: str | None = None) -> RunbookExecution | None:
        rb = self._runbooks.get(runbook_id)
        if rb is None:
            return None
        ex = RunbookExecution(id=_eid(), runbook_id=runbook_id,
                              incident_id=incident_id, actor=actor)
        # Record per-step intent; dispatch the first automation-bearing step.
        step_results = []
        dispatch_result = None
        for step in sorted(rb.steps, key=lambda s: s.order):
            entry = {"order": step.order, "title": step.title,
                     "automation_ref": step.automation_ref, "status": "noted"}
            if step.automation_ref and self._dispatcher is not None and dispatch_result is None:
                from app.models.domain import RemediationAction
                from app.models.enums import RiskLevel

                action = RemediationAction(
                    id=f"{ex.id}-{step.order}", problem_id=runbook_id,
                    title=step.title, description=step.description,
                    runbook=[s.title for s in rb.steps], risk=RiskLevel.MEDIUM,
                    estimated_mttr_minutes=5.0, requires_approval=False)
                dispatch_result = await self._dispatcher.dispatch(action, actor)
                entry["status"] = "dispatched" if dispatch_result.get("dispatched") else "logged"
            step_results.append(entry)
        ex = ex.model_copy(update={
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "step_results": step_results,
            "dispatch_result": dispatch_result,
        })
        self._executions[ex.id] = ex
        log.info("Runbook executed: %s by %s", runbook_id, actor)
        return ex

    def list_executions(self, runbook_id: str | None = None) -> list[RunbookExecution]:
        out = list(self._executions.values())
        if runbook_id:
            out = [e for e in out if e.runbook_id == runbook_id]
        return sorted(out, key=lambda e: e.started_at, reverse=True)
