"""P6 width modules persist to SQL and survive a service reload."""
from __future__ import annotations

import pytest

from app.repositories.sql.database import Database
from app.repositories.sql.width_stores import (
    ChangeEventSqlStore, DavisFeedbackSqlStore, PostmortemSqlStore,
    RunbookSqlStore,
)
from app.services.runbook_service import RunbookService
from app.services.postmortem_service import PostmortemService
from app.services.change_event_service import ChangeEventService
from app.services.davis_feedback_service import DavisFeedbackService
from app.models.postmortem import Postmortem
from app.models.change_event import ChangeEvent, ChangeType


@pytest.fixture
async def db(tmp_path):
    d = Database(f"sqlite+aiosqlite:///{tmp_path}/persist.db")
    await d.create_all()
    yield d
    await d.dispose()


@pytest.mark.asyncio
async def test_runbook_persists_across_reload(db):
    svc = RunbookService(persistence=RunbookSqlStore(db))
    await svc.load()  # seeds persisted on first load
    from app.models.runbook import Runbook
    created = await svc.create_runbook(Runbook(name="Persisted RB"))
    await svc.execute_runbook(created.id, actor="t")

    svc2 = RunbookService(persistence=RunbookSqlStore(db))
    await svc2.load()
    assert svc2.get_runbook(created.id) is not None
    assert any(e.runbook_id == created.id for e in svc2.list_executions())


@pytest.mark.asyncio
async def test_postmortem_persists(db):
    svc = PostmortemService(persistence=PostmortemSqlStore(db))
    await svc.load()
    pm = await svc.create(Postmortem(title="Outage"))
    await svc.add_timeline(pm.id, "alert fired", "sre")

    svc2 = PostmortemService(persistence=PostmortemSqlStore(db))
    await svc2.load()
    got = svc2.get(pm.id)
    assert got is not None and len(got.timeline) == 1


@pytest.mark.asyncio
async def test_change_event_persists(db):
    svc = ChangeEventService(persistence=ChangeEventSqlStore(db))
    await svc.load()
    ev = await svc.record(ChangeEvent(title="Deploy", service_id="SVC-X",
                                      change_type=ChangeType.DEPLOYMENT))
    await svc.link_incident(ev.id, "INC-1")

    svc2 = ChangeEventService(persistence=ChangeEventSqlStore(db))
    await svc2.load()
    got = svc2.get(ev.id)
    assert got is not None and "INC-1" in got.linked_incident_ids


@pytest.mark.asyncio
async def test_davis_feedback_persists(db):
    svc = DavisFeedbackService(persistence=DavisFeedbackSqlStore(db))
    await svc.load()
    await svc.record_feedback("P-1", True, "sre")
    await svc.record_feedback("P-1", True, "sre")

    svc2 = DavisFeedbackService(persistence=DavisFeedbackSqlStore(db))
    await svc2.load()
    assert svc2.rank("P-1") == 2.0


@pytest.mark.asyncio
async def test_in_memory_default_unchanged(tmp_path):
    """Without persistence the services still work purely in-memory."""
    svc = DavisFeedbackService()
    await svc.load()  # no-op
    await svc.record_feedback("P-9", True, "sre")
    assert svc.rank("P-9") == 1.0
