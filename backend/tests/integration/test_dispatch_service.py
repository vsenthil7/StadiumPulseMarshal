"""RemediationDispatcher: Cloud Workflows / AWX / webhook via MockTransport."""
from __future__ import annotations

import httpx
import pytest

from app.services.dispatch_service import RemediationDispatcher
from app.models.domain import RemediationAction
from app.models.enums import RiskLevel


def _action():
    return RemediationAction(
        id="RA-1", problem_id="P-1", title="Scale service",
        description="Add replicas", runbook=["s1", "s2"], risk=RiskLevel.LOW,
        estimated_mttr_minutes=5.0, requires_approval=True,
    )


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_no_backend_returns_not_dispatched():
    d = RemediationDispatcher()
    r = await d.dispatch(_action(), "sre@x")
    assert r["dispatched"] is False and r["target"] == "none"


@pytest.mark.asyncio
async def test_cloud_workflows_dispatch():
    d = RemediationDispatcher(
        cloud_workflows_url="https://workflows.googleapis.com/exec",
        http=_client(lambda req: httpx.Response(200, json={"name": "exec/123"})))
    r = await d.dispatch(_action(), "sre@x")
    assert r["dispatched"] is True and r["target"] == "cloud_workflows"
    assert "123" in r["response"]["name"]


@pytest.mark.asyncio
async def test_generic_webhook_dispatch():
    d = RemediationDispatcher(
        webhook_url="https://hooks.example/remediate",
        http=_client(lambda req: httpx.Response(200, json={"ok": True})))
    r = await d.dispatch(_action(), "sre@x")
    assert r["dispatched"] is True and r["target"] == "webhook"


@pytest.mark.asyncio
async def test_ansible_awx_dispatch():
    d = RemediationDispatcher(
        ansible_awx_url="https://awx.example", ansible_awx_token="tok",
        http=_client(lambda req: httpx.Response(201, json={"id": 42})))
    r = await d.dispatch(_action(), "sre@x")
    assert r["dispatched"] is True and r["target"] == "ansible_awx"
    assert r["response"]["id"] == 42


@pytest.mark.asyncio
async def test_cloud_workflows_network_error():
    def boom(req):
        raise httpx.ConnectError("down")
    d = RemediationDispatcher(
        cloud_workflows_url="https://workflows.googleapis.com/exec",
        http=_client(boom))
    r = await d.dispatch(_action(), "sre@x")
    assert r["dispatched"] is False and "error" in r
