"""Davis AI feedback loop.

Records SRE outcome feedback on Davis-surfaced problems (was the AI root cause
correct? did the remediation work?) and maintains a simple per-problem rank that
rises with confirmed-correct feedback and falls with incorrect — a lightweight
local stand-in for feeding outcomes back to Davis. Also exposes Davis analysis
(delegating to the Dynatrace client when available, else a synthetic analysis).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger

log = get_logger(__name__)


class DavisFeedbackService:
    def __init__(self, persistence=None) -> None:
        # problem_id → {"rank": float, "feedback": [ ... ]}
        self._state: dict[str, dict] = {}
        self._p = persistence

    async def load(self) -> None:
        if self._p is None:
            return
        self._state.update(await self._p.load())

    async def record_feedback(self, problem_id: str, correct: bool, actor: str,
                              notes: str = "") -> dict:
        entry = self._state.setdefault(problem_id, {"rank": 0.0, "feedback": []})
        entry["rank"] = round(entry["rank"] + (1.0 if correct else -1.0), 3)
        entry["feedback"].append({
            "correct": correct, "actor": actor, "notes": notes,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        if self._p is not None:
            await self._p.save(problem_id, entry["rank"], entry)
        log.info("Davis feedback for %s: correct=%s → rank=%s",
                 problem_id, correct, entry["rank"])
        return {"problem_id": problem_id, "rank": entry["rank"],
                "feedback_count": len(entry["feedback"])}

    def rank(self, problem_id: str) -> float:
        return self._state.get(problem_id, {}).get("rank", 0.0)

    def feedback_for(self, problem_id: str) -> list[dict]:
        return self._state.get(problem_id, {}).get("feedback", [])

    def ranked_problems(self) -> list[dict]:
        return sorted(
            ({"problem_id": pid, "rank": v["rank"],
              "feedback_count": len(v["feedback"])}
             for pid, v in self._state.items()),
            key=lambda r: r["rank"], reverse=True,
        )
