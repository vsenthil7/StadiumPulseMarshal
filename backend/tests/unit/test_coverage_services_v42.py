"""Coverage closeout part C: oncall_directory fallback, slack_signing edge
cases, remediation dispatch_service (cloud workflows / AWX / webhook)."""
from __future__ import annotations

import httpx
import pytest

from app.models.incident import EscalationTier
from app.models.notification import OnCallEngineer
from app.models.domain import RemediationAction
from app.services.oncall_directory import OnCallDirectory
from app.services.slack_signing import verify_slack_signature, sign_slack_request
from app.services.dispatch_service import (
    RemediationDispatcher, build_remediation_dispatcher,
)


# ── oncall_directory ──
def test_targets_for_severity_primary_and_secondary():
    roster = [
        OnCallEngineer(id="e3", name="Cmdr", tier=EscalationTier.TIER3,
                       handle="@cmdr", channels=["slack", "pagerduty"]),
        OnCallEngineer(id="e2", name="Sre", tier=EscalationTier.TIER2,
                       handle="@sre", channels=["email"]),
    ]
    d = OnCallDirectory(roster)
    page = d.targets_for_severity("page")
    assert [t.engineer_id for t in page] == ["e3", "e2"]
    # unknown channel falls back to EMAIL list default
    assert page[0].channels  # slack+pagerduty resolved


def test_targets_for_severity_fallback_to_any_tier():
    # Only a TIER1 engineer exists; 'page' maps to TIER3/TIER2 (vacant) → fallback
    roster = [OnCallEngineer(id="e1", name="Ops", tier=EscalationTier.TIER1,
                            handle="", channels=[])]
    d = OnCallDirectory(roster)
    page = d.targets_for_severity("page")
    assert len(page) == 1
    assert page[0].engineer_id == "e1"
    # empty handle → recipient falls back to id; no channels → EMAIL default
    assert page[0].recipient == "e1"
    from app.models.notification import NotificationChannel
    assert page[0].channels == [NotificationChannel.EMAIL]


def test_targets_for_unknown_severity_empty_roster():
    d = OnCallDirectory([])
    assert d.targets_for_severity("page") == []
    assert d.roster == []


# ── slack_signing ──
def test_slack_signature_disabled_without_secret():
    assert verify_slack_signature(
        signing_secret=None, timestamp="123", signature="v0=x",
        raw_body=b"body") is True


def test_slack_signature_missing_headers_false():
    assert verify_slack_signature(
        signing_secret="s", timestamp=None, signature=None,
        raw_body=b"body") is False


def test_slack_signature_bad_timestamp_false():
    assert verify_slack_signature(
        signing_secret="s", timestamp="not-an-int", signature="v0=x",
        raw_body=b"body") is False


def test_slack_signature_stale_false():
    assert verify_slack_signature(
        signing_secret="s", timestamp="1000", signature="v0=x",
        raw_body=b"body", now=999999.0) is False


def test_slack_signature_valid_roundtrip():
    secret = "shhh"
    ts = "1700000000"
    body = b"command=/spm&text=status"
    sig = sign_slack_request(secret, ts, body)
    assert verify_slack_signature(
        signing_secret=secret, timestamp=ts, signature=sig,
        raw_body=body, now=1700000010.0) is True


# ── dispatch_service ──
def _action():
    return RemediationAction(
        id="R-1", problem_id="P-1", title="Restart pool",
        description="bounce the saturated pool", runbook=["step1", "step2"],
    )


@pytest.mark.asyncio
async def test_dispatch_no_backend_configured():
    d = RemediationDispatcher()
    res = await d.dispatch(_action(), actor="sre-sam")
    assert res["dispatched"] is False and res["target"] == "none"
    await d.close()


@pytest.mark.asyncio
async def test_dispatch_cloud_workflows_success_and_failure():
    def ok(request):
        return httpx.Response(200, json={"name": "exec-123"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as http:
        d = RemediationDispatcher(cloud_workflows_url="https://cw.example", http=http)
        res = await d.dispatch(_action(), "sam")
        assert res["dispatched"] is True and res["target"] == "cloud_workflows"

    def boom(request):
        return httpx.Response(500, json={"error": "x"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
        d2 = RemediationDispatcher(cloud_workflows_url="https://cw.example", http=http)
        res2 = await d2.dispatch(_action(), "sam")
        assert res2["dispatched"] is False and "error" in res2


@pytest.mark.asyncio
async def test_dispatch_ansible_awx_success():
    def ok(request):
        assert request.headers.get("Authorization") == "Bearer tok"
        return httpx.Response(201, json={"id": 42})
    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as http:
        d = RemediationDispatcher(ansible_awx_url="https://awx.example",
                                  ansible_awx_token="tok", http=http)
        res = await d.dispatch(_action(), "sam")
        assert res["dispatched"] is True and res["target"] == "ansible_awx"


@pytest.mark.asyncio
async def test_dispatch_generic_webhook_success_and_failure():
    def ok(request):
        return httpx.Response(202)
    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as http:
        d = RemediationDispatcher(webhook_url="https://hook.example", http=http)
        res = await d.dispatch(_action(), "sam")
        assert res["dispatched"] is True and res["target"] == "webhook"

    def boom(request):
        raise httpx.ConnectError("down")
    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
        d2 = RemediationDispatcher(webhook_url="https://hook.example", http=http)
        res2 = await d2.dispatch(_action(), "sam")
        assert res2["dispatched"] is False and "error" in res2


def test_build_remediation_dispatcher_from_settings():
    class _S:
        cloud_workflows_url = "https://cw"
        ansible_awx_url = None
        ansible_awx_token = None
        remediation_webhook_url = None
    d = build_remediation_dispatcher(_S())
    assert d._cw_url == "https://cw"

