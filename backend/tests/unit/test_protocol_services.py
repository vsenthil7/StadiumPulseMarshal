"""Tests for MCP protocol/adapter, SLO engine, escalation, scenarios."""
from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.fixtures.scenarios.base import default_timeline, phase_for, kickoff_utc
from app.fixtures.scenarios.registry import (
    all_scenarios,
    get_scenario,
    list_scenario_keys,
)
from app.mcp.dynatrace_mcp_adapter import DynatraceMCPProtocolClient
from app.mcp.factory import build_observability_client
from app.mcp.protocol import MCPError, MCPSession, MCPTool
from app.models.enums import MatchdayPhase, Severity
from app.models.slo import SLI, SLO, SLIKind, SLOMeasurement
from app.services.escalation_engine import EscalationEngine
from app.services.ops_defaults import (
    default_escalation_policies,
    default_on_call,
    synthetic_measurement,
)
from app.services.slo_engine import SLOEngine, compute_error_budget
from app.models.incident import EscalationTier, Incident


def _mcp_handler(req: httpx.Request) -> httpx.Response:
    body = json.loads(req.content)
    method, rid = body["method"], body["id"]
    if method == "initialize":
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
                              "result": {"serverInfo": {"name": "dt-mcp"}}})
    if method == "tools/list":
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid, "result": {
            "tools": [{"name": "list_problems", "description": "d",
                       "inputSchema": {}}]}})
    if method == "tools/call":
        name = body["params"]["name"]
        if name == "list_problems":
            payload = {"problems": [{"problemId": "P1", "title": "x",
                       "severityLevel": "ERROR", "status": "OPEN",
                       "startTime": 1700000000000}]}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text",
                           "text": json.dumps(payload)}]}})
        if name == "get_problem_details":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text",
                           "text": json.dumps({"problemId": "P1", "title": "x",
                           "severityLevel": "ERROR", "status": "OPEN"})}]}})
        if name == "list_entities":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text",
                           "text": json.dumps({"entities": [{"entityId": "E",
                           "displayName": "svc", "type": "SERVICE"}]})}]}})
        if name == "get_metrics":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text",
                           "text": json.dumps({"result": []})}]}})
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
        "error": {"code": -32601, "message": "not found"}})


def _session() -> MCPSession:
    http = httpx.AsyncClient(transport=httpx.MockTransport(_mcp_handler))
    return MCPSession("https://mcp/rpc", http)


async def test_mcp_session_handshake_and_tools():
    s = _session()
    await s.initialize()
    assert s.initialized
    assert s.server_info["name"] == "dt-mcp"
    tools = await s.list_tools()
    assert tools[0].name == "list_problems"
    assert "list_problems" in repr(tools[0])


async def test_mcp_error():
    s = _session()
    with pytest.raises(MCPError) as ei:
        await s.call_tool("nope")
    assert ei.value.code == -32601


async def test_mcp_content_extraction_non_json():
    # text that isn't JSON returns the raw string
    def handler(req):
        body = json.loads(req.content)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
            "result": {"content": [{"type": "text", "text": "plain text"}]}})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    s = MCPSession("https://mcp/rpc", http)
    assert await s.call_tool("x") == "plain text"


async def test_mcp_content_empty_returns_result():
    def handler(req):
        body = json.loads(req.content)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
            "result": {"content": []}})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    s = MCPSession("https://mcp/rpc", http)
    assert await s.call_tool("x") == {"content": []}


def test_mcp_tool_from_payload():
    t = MCPTool.from_payload({"name": "n", "description": "d",
                              "inputSchema": {"x": 1}})
    assert t.name == "n" and t.input_schema == {"x": 1}


async def test_adapter_via_protocol():
    client = DynatraceMCPProtocolClient(_session())
    assert client.mode == "live-mcp"
    probs = await client.list_problems(open_only=True)
    assert probs[0].id == "P1"
    assert (await client.get_problem("P1")).id == "P1"
    ents = await client.list_entities()
    assert ents[0].name == "svc"
    metrics = await client.get_metrics("E")
    assert metrics == []
    assert len(await client.get_fixture_timeline()) == 7


def test_adapter_as_list_helper():
    assert DynatraceMCPProtocolClient._as_list({"k": [1]}, "k") == [1]
    assert DynatraceMCPProtocolClient._as_list([1, 2], "k") == [1, 2]
    assert DynatraceMCPProtocolClient._as_list("x", "k") == []


def test_adapter_create_and_factory():
    s = Settings(use_mocks=False, dt_tenant_url="https://x.live.dynatrace.com",
                 dt_api_token="t", dt_mcp_url="https://mcp/rpc")
    client = build_observability_client(s)
    assert isinstance(client, DynatraceMCPProtocolClient)
    # create() builds its own http client
    c2 = DynatraceMCPProtocolClient.create(s)
    assert c2.mode == "live-mcp"


async def test_adapter_get_problem_empty():
    def handler(req):
        body = json.loads(req.content)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                "result": {"serverInfo": {}}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
            "result": {"content": [{"type": "text", "text": "[]"}]}})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DynatraceMCPProtocolClient(MCPSession("https://mcp/rpc", http))
    assert await client.get_problem("X") is None


# --- SLO engine ---
def test_slo_engine_classification():
    sli = SLI(key="a", kind=SLIKind.AVAILABILITY, entity_id="SVC")
    slo = SLO(id="S", name="n", service_id="SVC", sli=sli, target=0.99,
              window_hours=24)
    # Healthy: error 0.3% vs 1% budget -> burn 0.3x
    healthy = compute_error_budget(
        slo, SLOMeasurement(slo_id="S", good_events=9970, total_events=10000))
    assert healthy.state.value == "HEALTHY"
    assert healthy.burn_rate < 1.0
    # Slow burn: error 1.4% -> burn 1.4x
    slow = compute_error_budget(
        slo, SLOMeasurement(slo_id="S", good_events=9860, total_events=10000))
    assert slow.state.value == "SLOW_BURN"
    assert 1.0 <= slow.burn_rate < 2.0
    # Fast burn: error 3% -> burn 3x (consumed still < 1 over 1h window)
    fast = compute_error_budget(
        slo, SLOMeasurement(slo_id="S", good_events=9700, total_events=10000,
                            observation_window_hours=1.0))
    assert fast.state.value == "FAST_BURN"
    assert fast.burn_rate >= 2.0
    assert fast.consumed_fraction < 1.0
    # Exhausted: slow-ish burn but over the full window -> consumed >= 1
    exhausted = compute_error_budget(
        slo, SLOMeasurement(slo_id="S", good_events=9880, total_events=10000,
                            observation_window_hours=24.0))
    assert exhausted.state.value == "EXHAUSTED"
    assert exhausted.consumed_fraction >= 1.0


def test_slo_measurement_error_rate():
    m = SLOMeasurement(slo_id="S", good_events=98, total_events=100)
    assert m.error_rate == 0.02
    empty = SLOMeasurement(slo_id="S", good_events=0, total_events=0)
    assert empty.error_rate == 0.0


def test_slo_engine_100pct_target():
    sli = SLI(key="a", kind=SLIKind.AVAILABILITY, entity_id="SVC")
    slo = SLO(id="S", name="n", service_id="SVC", sli=sli, target=1.0)
    perfect = compute_error_budget(slo, SLOMeasurement(slo_id="S", good_events=100, total_events=100))
    assert perfect.state.value == "HEALTHY"
    # Any error against a 100% target is an infinite burn rate -> FAST_BURN.
    any_err = compute_error_budget(slo, SLOMeasurement(slo_id="S", good_events=99, total_events=100))
    assert any_err.state.value == "FAST_BURN"
    assert any_err.burn_rate == 9999.0
    assert any_err.consumed_fraction >= 1.0


def test_slo_engine_evaluate_and_worst():
    sli = SLI(key="a", kind=SLIKind.AVAILABILITY, entity_id="SVC")
    slo = SLO(id="S", name="n", service_id="SVC", sli=sli, target=0.99,
              window_hours=24)
    engine = SLOEngine([slo])
    assert engine.get("S") is slo
    assert engine.get("missing") is None
    budgets = engine.evaluate([
        SLOMeasurement(slo_id="S", good_events=9880, total_events=10000,
                       observation_window_hours=24.0),
        SLOMeasurement(slo_id="UNKNOWN", good_events=1, total_events=1),
    ])
    assert len(budgets) == 1
    # Sustained error over the full window -> EXHAUSTED is the worst.
    assert engine.worst(budgets).state.value == "EXHAUSTED"
    assert engine.worst([]) is None


# --- escalation engine ---
def test_escalation_engine_no_policy():
    eng = EscalationEngine([], [])
    inc = Incident(id="I", problem_id="P", title="t", severity=Severity.LOW)
    decision = eng.evaluate(inc, 100)
    assert decision.should_escalate is False


def test_escalation_engine_routes():
    eng = EscalationEngine(default_escalation_policies(), default_on_call())
    inc = Incident(id="I", problem_id="P", title="t", severity=Severity.CRITICAL,
                   tier=EscalationTier.TIER1)
    decision = eng.evaluate(inc, 20)
    assert decision.should_escalate is True
    assert decision.engineer is not None
    assert eng.on_call_for(EscalationTier.TIER3) is not None


def test_escalation_engine_no_step_yet():
    eng = EscalationEngine(default_escalation_policies(), default_on_call())
    inc = Incident(id="I", problem_id="P", title="t", severity=Severity.MEDIUM,
                   tier=EscalationTier.TIER2)
    # standard policy first step at 0min is TIER1 < current TIER2 -> no escalate
    decision = eng.evaluate(inc, 0)
    assert decision.should_escalate is False


# --- ops defaults ---
def test_synthetic_measurement_variants():
    # Build SLOs whose ids hash to each branch.
    for tid in ["SLO-AAA", "SLO-AAB", "SLO-AAC"]:
        sli = SLI(key="a", kind=SLIKind.AVAILABILITY, entity_id="SVC")
        slo = SLO(id=tid, name="n", service_id="SVC", sli=sli, target=0.99)
        m = synthetic_measurement(slo)
        assert m.total_events == 10000
        assert 0 <= m.good_events <= 10000


# --- scenarios ---
def test_scenario_registry():
    keys = list_scenario_keys()
    assert len(keys) == 4
    assert get_scenario("k8s_oom").key == "k8s_oom"
    # unknown falls back to default
    assert get_scenario("nonexistent").key == "payment_db_saturation"
    assert len(all_scenarios()) == 4


def test_scenario_timeline_phase_for():
    k = kickoff_utc(day=13, hour=20)
    tl = default_timeline(k)
    from datetime import timedelta
    assert phase_for(tl, k - timedelta(hours=3)) == MatchdayPhase.PRE_GATES
    assert phase_for(tl, k + timedelta(minutes=46)) == MatchdayPhase.HALFTIME
    assert phase_for(tl, k + timedelta(minutes=300)) == MatchdayPhase.POST_MATCH


def test_all_scenarios_have_content():
    for s in all_scenarios():
        assert s.problems
        assert s.entities
        assert s.venue.capacity > 0
        assert s.problems[0].severity in list(Severity)
