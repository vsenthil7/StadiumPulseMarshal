"""Agent reasoning layer — base interface and deterministic mock agent."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.domain import AgentAnalysis, Problem, RootCauseNode
from app.services.remediation import plan_remediations


class ReasoningAgent(ABC):
    """Produces an analysis (root cause + recommendations) for a problem."""

    @property
    @abstractmethod
    def backend(self) -> str:
        ...

    @abstractmethod
    async def analyze(self, problem: Problem) -> AgentAnalysis:
        ...


def _deepest_root_cause(node: RootCauseNode | None) -> RootCauseNode | None:
    """Return the node flagged as the true root cause, if any."""
    found: RootCauseNode | None = None
    stack = [node] if node else []
    while stack:
        cur = stack.pop()
        if cur.is_root_cause:
            found = cur
        stack.extend(cur.children)
    return found


class MockReasoningAgent(ReasoningAgent):
    """Deterministic reasoning used when Gemini is unavailable.

    Mirrors how the live agent reasons: localise root cause, correlate with the
    matchday phase, and attach ranked remediations — but with fixed text so the
    demo and tests are stable.
    """

    @property
    def backend(self) -> str:
        return "mock"

    async def analyze(self, problem: Problem) -> AgentAnalysis:
        root = _deepest_root_cause(problem.root_cause)
        actions = plan_remediations(problem)
        phase = problem.matchday_phase

        if root is not None:
            confidence = root.confidence
            summary = (
                f"Root cause localised to {root.entity_name} "
                f"({root.entity_type.value}). {root.contribution}"
            )
            reasoning = (
                f"Davis AI causal analysis points to {root.entity_name} with "
                f"{int(root.confidence * 100)}% confidence. This coincides with "
                f"the {phase.value if phase else 'current'} matchday phase, when "
                "load multiplies sharply, consistent with a surge-driven "
                "saturation rather than a code regression."
            )
        else:
            confidence = 0.4
            summary = (
                "No single causal entity flagged; correlated symptoms across "
                "affected services."
            )
            reasoning = (
                "No high-confidence root cause from Davis AI; recommending "
                "human triage with the assembled context."
            )

        return AgentAnalysis(
            problem_id=problem.id,
            summary=summary,
            root_cause=root or problem.root_cause,
            correlated_phase=phase,
            confidence=confidence,
            recommended_actions=actions,
            reasoning=reasoning,
            generated_by="mock",
        )
