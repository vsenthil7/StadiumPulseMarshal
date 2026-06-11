"""Repository contract tests run against both memory and SQL backends."""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.models.domain import ApprovalDecision, RemediationAction
from app.models.enums import RemediationStatus, RiskLevel
from app.models.incident import Incident, IncidentState
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)
from app.models.slo import BurnState, ErrorBudget
from app.models.enums import Severity
from app.repositories.factory import build_repositories


@pytest.fixture(params=["memory", "sql"])
async def repos(request):
    if request.param == "memory":
        bundle = build_repositories(Settings())
    else:
        bundle = build_repositories(
            Settings(database_url="sqlite+aiosqlite:///:memory:")
        )
    await bundle.init()
    yield bundle
    await bundle.dispose()


async def test_incident_repo(repos):
    inc = Incident(id="I1", problem_id="P1", title="t", severity=Severity.HIGH,
                   venue_id="V1")
    await repos.incidents.add(inc)
    got = await repos.incidents.get("I1")
    assert got.title == "t"
    assert await repos.incidents.get("missing") is None
    inc.state = IncidentState.RESOLVED
    from datetime import datetime, timezone
    inc.resolved_at = datetime.now(timezone.utc)
    await repos.incidents.update(inc)
    assert await repos.incidents.count() == 1
    assert await repos.incidents.count(open_only=True) == 0
    assert len(await repos.incidents.list(venue_id="V1")) == 1
    assert len(await repos.incidents.list(venue_id="other")) == 0
    assert len(await repos.incidents.list(offset=5, limit=10)) == 0


async def test_incident_repo_update_creates_when_absent(repos):
    inc = Incident(id="I-NEW", problem_id="P", title="t", severity=Severity.LOW)
    await repos.incidents.update(inc)  # update path with no prior add
    assert await repos.incidents.get("I-NEW") is not None


async def test_remediation_repo(repos):
    a = RemediationAction(id="RA1", problem_id="P1", title="fix", description="d",
                          risk=RiskLevel.LOW)
    await repos.remediations.add_many([a, a])  # idempotent
    assert (await repos.remediations.get("RA1")).title == "fix"
    assert await repos.remediations.get("missing") is None
    assert len(await repos.remediations.list(pending=True)) == 1
    a.status = RemediationStatus.APPROVED
    await repos.remediations.update(a)
    assert len(await repos.remediations.list(pending=True)) == 0
    assert len(await repos.remediations.list()) == 1


async def test_remediation_update_creates_when_absent(repos):
    a = RemediationAction(id="RA-NEW", problem_id="P", title="t", description="d")
    await repos.remediations.update(a)
    assert await repos.remediations.get("RA-NEW") is not None


async def test_audit_repo(repos):
    d = ApprovalDecision(remediation_id="RA1", approved=True, decided_by="jane")
    await repos.audit.add(d)
    items = await repos.audit.list()
    assert len(items) == 1
    assert items[0].decided_by == "jane"


async def test_notification_repo(repos):
    n = Notification(id="N1", incident_id="I1",
                     channel=NotificationChannel.EMAIL, recipient="a",
                     subject="s", body="b")
    await repos.notifications.add(n)
    n.status = NotificationStatus.SENT
    await repos.notifications.update(n)
    assert len(await repos.notifications.list(incident_id="I1")) == 1
    assert len(await repos.notifications.list(incident_id="other")) == 0
    assert len(await repos.notifications.list()) == 1


async def test_notification_update_creates_when_absent(repos):
    n = Notification(id="N-NEW", incident_id="I1",
                     channel=NotificationChannel.SLACK, recipient="a",
                     subject="s", body="b")
    await repos.notifications.update(n)
    assert len(await repos.notifications.list()) == 1


async def test_slo_repo(repos):
    b = ErrorBudget(slo_id="S1", slo_name="n", target=0.99, achieved=0.999,
                    consumed_fraction=0.1, remaining_fraction=0.9,
                    burn_rate=0.1, state=BurnState.HEALTHY)
    await repos.slo.save_budget(b)
    await repos.slo.save_budget(b)  # upsert
    budgets = await repos.slo.list_budgets()
    assert len(budgets) == 1
    assert budgets[0].slo_id == "S1"
