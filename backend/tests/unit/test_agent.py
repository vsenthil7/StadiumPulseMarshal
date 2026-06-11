"""Tests for the reasoning agents and agent factory."""
from __future__ import annotations

import pytest

from app.agent.base import MockReasoningAgent, _deepest_root_cause
from app.agent.factory import build_agent
from app.agent.gemini_agent import (
    GeminiReasoningAgent,
    build_prompt,
    parse_response,
)
from app.core.config import Settings
from app.fixtures import matchday
from app.models.domain import Problem, RootCauseNode
from app.models.enums import EntityType, ProblemStatus, Severity
from app.services.remediation import plan_remediations


async def test_mock_agent_with_root_cause():
    agent = MockReasoningAgent()
    assert agent.backend == "mock"
    p = matchday.problems()[0]
    a = await agent.analyze(p)
    assert a.confidence == 0.91
    assert a.generated_by == "mock"
    assert "payments-postgres" in a.summary
    assert len(a.recommended_actions) == 2


async def test_mock_agent_without_root_cause():
    agent = MockReasoningAgent()
    p = Problem(id="p", title="t", severity=Severity.MEDIUM,
                status=ProblemStatus.OPEN)
    a = await agent.analyze(p)
    assert a.confidence == 0.4
    assert "human triage" in a.reasoning.lower()


def test_deepest_root_cause_none():
    assert _deepest_root_cause(None) is None


def test_deepest_root_cause_finds_flagged():
    leaf = RootCauseNode(entity_id="DB", entity_name="db",
                         entity_type=EntityType.DATABASE, is_root_cause=True,
                         confidence=0.9)
    root = RootCauseNode(entity_id="S", entity_name="s",
                         entity_type=EntityType.SERVICE, children=[leaf])
    found = _deepest_root_cause(root)
    assert found.entity_id == "DB"


def test_build_prompt_contains_facts():
    p = matchday.problems()[0]
    actions = plan_remediations(p)
    candidates = [{"id": a.id, "title": a.title} for a in actions]
    prompt = build_prompt(p, candidates)
    assert "payments-postgres" in prompt
    assert "HALFTIME" in prompt


def test_build_prompt_without_root_cause():
    p = Problem(id="p", title="t", severity=Severity.LOW,
                status=ProblemStatus.OPEN)
    prompt = build_prompt(p, [])
    assert '"root_cause": null' in prompt


def test_parse_response_plain_json():
    p = matchday.problems()[0]
    actions = plan_remediations(p)
    text = (
        '{"summary":"s","confidence":0.8,"reasoning":"r",'
        f'"ranked_action_ids":["{actions[1].id}"]}}'
    )
    a = parse_response(text, p, actions)
    assert a.generated_by == "gemini"
    assert a.recommended_actions[0].id == actions[1].id
    # omitted action appended for completeness
    assert actions[0] in a.recommended_actions


def test_parse_response_with_code_fence():
    p = matchday.problems()[0]
    actions = plan_remediations(p)
    text = (
        "```json\n"
        '{"summary":"s","confidence":0.5,"reasoning":"r","ranked_action_ids":[]}'
        "\n```"
    )
    a = parse_response(text, p, actions)
    assert a.confidence == 0.5
    assert len(a.recommended_actions) == len(actions)


def test_factory_returns_mock_without_creds():
    agent = build_agent(Settings(use_mocks=True))
    assert isinstance(agent, MockReasoningAgent)


def test_factory_falls_back_when_gemini_init_fails(monkeypatch):
    s = Settings(use_mocks=False, google_api_key="key")

    def boom(_settings):
        raise RuntimeError("no sdk")

    monkeypatch.setattr(GeminiReasoningAgent, "create", staticmethod(boom))
    agent = build_agent(s)
    assert isinstance(agent, MockReasoningAgent)


async def test_gemini_agent_analyze_with_fake_client():
    s = Settings(use_mocks=False, google_api_key="key")
    p = matchday.problems()[0]
    actions_preview = plan_remediations(p)

    class FakeResp:
        text = (
            '{"summary":"db saturated","confidence":0.93,'
            '"reasoning":"halftime surge",'
            f'"ranked_action_ids":["{actions_preview[0].id}"]}}'
        )

    class FakeModels:
        async def generate_content(self, **kwargs):
            assert "payments-postgres" in kwargs["contents"]
            return FakeResp()

    class FakeAio:
        models = FakeModels()

    class FakeClient:
        aio = FakeAio()

    agent = GeminiReasoningAgent(s, FakeClient())
    assert agent.backend == "gemini"
    a = await agent.analyze(p)
    assert a.confidence == 0.93
    assert a.generated_by == "gemini"


def test_gemini_create_requires_sdk():
    s = Settings(use_mocks=False, google_api_key="key")
    with pytest.raises(Exception):
        GeminiReasoningAgent.create(s)
