"""Live Gemini-backed reasoning agent (Google ADK / GenAI).

Follows the Agent Builder pattern: the matchday context and candidate
remediations (produced deterministically by the remediation service) are passed
to Gemini, which selects, ranks and explains — grounding the LLM in real
Dynatrace-derived facts rather than asking it to hallucinate infrastructure.

The Google GenAI SDK is an optional dependency. If it is not installed or no
credentials are present, construction raises and the factory falls back to the
mock agent. The prompt assembly and response parsing are split into pure helpers
so they are unit-testable without the SDK.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.domain import AgentAnalysis, Problem
from app.services.remediation import plan_remediations
from app.agent.base import ReasoningAgent, _deepest_root_cause

log = get_logger(__name__)

SYSTEM_INSTRUCTION = (
    "You are StadiumPulse Marshal, an AIOps agent for 2026 World Cup matchday "
    "operations. You receive a Dynatrace problem with Davis AI root-cause data "
    "and a list of candidate remediation actions. Correlate the root cause with "
    "the matchday phase, choose and rank the most appropriate remediations, and "
    "explain your reasoning concisely for an SRE. Respond ONLY with JSON of the "
    "form: {\"summary\": str, \"confidence\": float, \"reasoning\": str, "
    "\"ranked_action_ids\": [str]}. Never invent actions outside the candidates."
)


def build_prompt(problem: Problem, candidates: list[dict[str, Any]]) -> str:
    """Assemble the user prompt grounding Gemini in real facts."""
    root = _deepest_root_cause(problem.root_cause)
    payload = {
        "problem": {
            "id": problem.id,
            "title": problem.title,
            "severity": problem.severity.value,
            "matchday_phase": (
                problem.matchday_phase.value if problem.matchday_phase else None
            ),
            "impact": problem.impact_summary,
            "root_cause": (
                {
                    "entity": root.entity_name,
                    "type": root.entity_type.value,
                    "confidence": root.confidence,
                    "contribution": root.contribution,
                }
                if root
                else None
            ),
            "events": [
                {"title": e.title, "description": e.description}
                for e in problem.events
            ],
        },
        "candidate_actions": candidates,
    }
    return json.dumps(payload, indent=2)


def parse_response(
    text: str,
    problem: Problem,
    actions: list,
) -> AgentAnalysis:
    """Parse Gemini JSON into an AgentAnalysis, ranking actions accordingly."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    data = json.loads(cleaned)

    by_id = {a.id: a for a in actions}
    ranked_ids = data.get("ranked_action_ids", [])
    ranked = [by_id[i] for i in ranked_ids if i in by_id]
    # Append any candidate the model omitted, preserving completeness.
    for a in actions:
        if a not in ranked:
            ranked.append(a)

    return AgentAnalysis(
        problem_id=problem.id,
        summary=data.get("summary", ""),
        root_cause=_deepest_root_cause(problem.root_cause) or problem.root_cause,
        correlated_phase=problem.matchday_phase,
        confidence=float(data.get("confidence", 0.5)),
        recommended_actions=ranked,
        reasoning=data.get("reasoning", ""),
        generated_by="gemini",
    )


class GeminiReasoningAgent(ReasoningAgent):
    """Reasoning agent backed by Gemini via the Google GenAI SDK."""

    def __init__(self, settings: Settings, client: Any) -> None:
        self._settings = settings
        self._client = client

    @classmethod
    def create(cls, settings: Settings) -> "GeminiReasoningAgent":
        from google import genai  # type: ignore

        if settings.google_api_key:
            client = genai.Client(api_key=settings.google_api_key)
        else:
            client = genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
            )
        return cls(settings, client)

    @property
    def backend(self) -> str:
        return "gemini"

    async def analyze(self, problem: Problem) -> AgentAnalysis:
        actions = plan_remediations(problem)
        candidates = [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "risk": a.risk.value,
                "estimated_mttr_minutes": a.estimated_mttr_minutes,
            }
            for a in actions
        ]
        prompt = build_prompt(problem, candidates)
        resp = await self._client.aio.models.generate_content(
            model=self._settings.gemini_model,
            contents=prompt,
            config={"system_instruction": SYSTEM_INSTRUCTION},
        )
        return parse_response(resp.text, problem, actions)
