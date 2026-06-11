"""Targeted tests closing the final coverage branches."""
from __future__ import annotations

import json

import httpx

from app.fixtures.scenarios.registry import get_scenario
from app.mcp.dynatrace_mcp_adapter import DynatraceMCPProtocolClient
from app.mcp.mock_client import MockMCPClient
from app.mcp.protocol import MCPSession
from app.models.incident import Incident
from app.models.enums import Severity
from app.services.analytics import compute_summary
from app.services.escalation_engine import EscalationEngine
from app.services.ops_defaults import default_escalation_policies, default_on_call


async def test_mock_client_unknown_entity_metric():
    c = MockMCPClient()
    # An entity id not present in the scenario hits the fallback branch.
    metrics = await c.get_metrics("DOES-NOT-EXIST")
    assert metrics[0].latest == 10.0


def test_analytics_counts_open_incident():
    inc = Incident(id="I", problem_id="P", title="t", severity=Severity.HIGH)
    summary = compute_summary([inc], [])
    assert summary.open_incidents == 1
    assert summary.resolved_incidents == 0


def test_escalation_no_step_elapsed_branch():
    eng = EscalationEngine(default_escalation_policies(), default_on_call())
    inc = Incident(id="I", problem_id="P", title="t", severity=Severity.HIGH)
    # Critical policy first step is at 0 min; use a policy whose steps are all
    # in the future by evaluating at a negative-equivalent (0 elapsed but all
    # steps require >0). Build such a policy inline.
    from app.models.notification import EscalationPolicy, EscalationStep
    from app.models.incident import EscalationTier
    future = EscalationPolicy(
        id="F", name="future", min_severity=Severity.HIGH,
        steps=[EscalationStep(tier=EscalationTier.TIER2, after_minutes=99)])
    eng2 = EscalationEngine([future], default_on_call())
    decision = eng2.evaluate(inc, 0)
    assert decision.should_escalate is False


async def _adapter_with(handler) -> DynatraceMCPProtocolClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DynatraceMCPProtocolClient(MCPSession("https://mcp/rpc", http))


async def test_adapter_get_problem_returns_parsed_dict():
    def handler(req):
        body = json.loads(req.content)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                "result": {"serverInfo": {}}})
        # Return a populated problem dict (not empty) -> parse path (line 80).
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
            "result": {"content": [{"type": "text", "text": json.dumps(
                {"problemId": "P9", "title": "t", "severityLevel": "ERROR",
                 "status": "OPEN"})}]}})
    client = await _adapter_with(handler)
    prob = await client.get_problem("P9")
    assert prob is not None
    assert prob.id == "P9"


async def test_adapter_get_problem_non_dict_returns_none():
    def handler(req):
        body = json.loads(req.content)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                "result": {"serverInfo": {}}})
        # Truthy but non-dict (populated list) -> falls through to None (line 80).
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
            "result": {"content": [{"type": "text", "text": json.dumps([1, 2, 3])}]}})
    client = await _adapter_with(handler)
    assert await client.get_problem("X") is None


async def test_adapter_get_metrics_non_dict_returns_empty():
    def handler(req):
        body = json.loads(req.content)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                "result": {"serverInfo": {}}})
        # Return a JSON list (non-dict) so the metrics branch returns [] (line 97).
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
            "result": {"content": [{"type": "text", "text": json.dumps([1, 2])}]}})
    client = await _adapter_with(handler)
    assert await client.get_metrics("E") == []


def test_scenario_slos_present():
    # Touches scenario SLO wiring used by the context.
    s = get_scenario("payment_db_saturation")
    assert len(s.slos) == 2
