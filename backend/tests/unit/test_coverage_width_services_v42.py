"""Coverage for width-module services: change_event, runbook, postmortem."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from app.models.change_event import ChangeEvent, ChangeType
from app.models.postmortem import Postmortem, PostmortemStatus
from app.services.change_event_service import ChangeEventService
from app.services.runbook_service import RunbookService
from app.services.postmortem_service import PostmortemService


# ── change_event_service ──
@pytest.mark.asyncio
async def test_change_event_record_list_get_correlate_link():
    svc = ChangeEventService(correlation_window_minutes=60)
    now = datetime.now(timezone.utc)
    ev = await svc.record(ChangeEvent(title="deploy api", service_id="svc-api",
                                      change_type=ChangeType.DEPLOYMENT, at=now))
    assert ev.id  # auto-assigned
    # list + filters
    assert len(svc.list()) == 1
    assert len(svc.list(service_id="svc-api")) == 1
    assert svc.list(service_id="other") == []
    assert len(svc.list(change_type=ChangeType.DEPLOYMENT)) == 1
    # get
    assert svc.get(ev.id) is not None
    assert svc.get("missing") is None
    # correlate within window
    corr = svc.correlate(now + timedelta(minutes=5), service_id="svc-api")
    assert len(corr) == 1
    # outside window
    assert svc.correlate(now + timedelta(hours=5)) == []
    # link incident (and idempotent re-link)
    linked = await svc.link_incident(ev.id, "INC-1")
    assert "INC-1" in linked.linked_incident_ids
    again = await svc.link_incident(ev.id, "INC-1")
    assert again.linked_incident_ids.count("INC-1") == 1
    assert await svc.link_incident("missing", "INC-9") is None


# ── runbook_service ──
@pytest.mark.asyncio
async def test_runbook_list_get_crud_and_execute():
    svc = RunbookService()
    # seeded
    all_rb = svc.list_runbooks()
    assert len(all_rb) >= 2
    # filters
    from app.models.runbook import RunbookCategory
    assert all(r.category == RunbookCategory.DATABASE
               for r in svc.list_runbooks(category=RunbookCategory.DATABASE))
    assert svc.list_runbooks(tag="matchday")
    assert isinstance(svc.list_runbooks(venue_id="venue_arena_north"), list)
    # get
    assert svc.get_runbook("RB-db-pool-scale") is not None
    assert svc.get_runbook("nope") is None
    # update missing
    assert await svc.update_runbook("nope", {"name": "x"}) is None
    # update existing → version bump
    up = await svc.update_runbook("RB-db-pool-scale", {"description": "v2"})
    assert up.version == 2 and up.description == "v2"
    # delete
    assert await svc.delete_runbook("RB-svc-scaleout") is True
    assert await svc.delete_runbook("RB-svc-scaleout") is False
    # execute missing
    assert await svc.execute_runbook("nope", actor="sam") is None
    # execute existing (no dispatcher → steps noted/logged)
    ex = await svc.execute_runbook("RB-db-pool-scale", actor="sam", incident_id="INC-1")
    assert ex.status == "completed"
    assert svc.list_executions("RB-db-pool-scale")
    assert isinstance(svc.list_executions(), list)


class _OkDispatcher:
    async def dispatch(self, action, actor):
        return {"dispatched": True, "target": "cloud_workflows"}


@pytest.mark.asyncio
async def test_runbook_execute_with_dispatcher_marks_dispatched():
    svc = RunbookService(dispatcher=_OkDispatcher())
    ex = await svc.execute_runbook("RB-db-pool-scale", actor="sam")
    # the automation-bearing step should be dispatched
    statuses = [s["status"] for s in ex.step_results]
    assert "dispatched" in statuses
    assert ex.dispatch_result is not None


# ── postmortem_service ──
@pytest.mark.asyncio
async def test_postmortem_full_lifecycle_and_export():
    svc = PostmortemService()
    pm = await svc.create(Postmortem(title="DB outage", incident_id="INC-1",
                                     severity="SEV1", summary="pool exhausted"))
    assert pm.id
    # list + filters
    assert len(svc.list()) == 1
    assert len(svc.list(status=PostmortemStatus.DRAFT)) == 1
    assert len(svc.list(incident_id="INC-1")) == 1
    # get
    assert svc.get(pm.id) is not None
    assert svc.get("missing") is None
    # update missing
    assert await svc.update("missing", {"summary": "x"}) is None
    # timeline + action + complete
    pm2 = await svc.add_timeline(pm.id, "alert fired", "sam")
    assert len(pm2.timeline) == 1
    assert await svc.add_timeline("missing", "x", "y") is None
    pm3 = await svc.add_action(pm.id, "add capacity alarm", owner="sam")
    assert len(pm3.action_items) == 1
    assert await svc.add_action("missing", "x") is None
    aid = pm3.action_items[0].id
    pm4 = await svc.complete_action(pm.id, aid)
    assert pm4.action_items[0].done is True
    assert await svc.complete_action("missing", aid) is None
    # publish
    pub = await svc.publish(pm.id)
    assert pub.status == PostmortemStatus.PUBLISHED
    # export markdown
    md = svc.export_markdown(pm.id)
    assert md.startswith("# Postmortem: DB outage")
    assert "## Timeline" in md and "## Action items" in md
    assert svc.export_markdown("missing") is None

