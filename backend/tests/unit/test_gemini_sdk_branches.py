"""Cover the live Gemini construction branches using an injected fake SDK module.

The real ``google.genai`` SDK makes network calls and is an optional dependency,
so we inject a stand-in module into ``sys.modules`` to exercise both
client-construction branches (API key vs Vertex ADC) and the factory success
path deterministically.
"""
from __future__ import annotations

import sys
import types

import pytest

from app.agent.factory import build_agent
from app.agent.gemini_agent import GeminiReasoningAgent
from app.core.config import Settings


@pytest.fixture
def fake_genai(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    genai_mod = types.SimpleNamespace(Client=FakeClient)
    google_pkg = types.ModuleType("google")
    google_pkg.genai = genai_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    return captured


def test_create_with_api_key(fake_genai):
    s = Settings(use_mocks=False, google_api_key="key-123")
    agent = GeminiReasoningAgent.create(s)
    assert agent.backend == "gemini"
    assert fake_genai["api_key"] == "key-123"


def test_create_with_vertex(fake_genai):
    s = Settings(
        use_mocks=False,
        google_application_credentials="/tmp/c.json",
        google_cloud_project="proj",
        google_cloud_location="europe-west2",
    )
    GeminiReasoningAgent.create(s)
    assert fake_genai["vertexai"] is True
    assert fake_genai["project"] == "proj"


def test_factory_uses_gemini_when_available(fake_genai):
    s = Settings(use_mocks=False, google_api_key="key-123")
    agent = build_agent(s)
    assert isinstance(agent, GeminiReasoningAgent)
    assert agent.backend == "gemini"
