"""Postmortem workflow service: create/update/timeline/actions/export.

Optional ``persistence`` (PostmortemSqlStore) makes records durable; without it
the service is purely in-memory (default for mock/demo and DB-less tests).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.models.postmortem import (
    ActionItem, Postmortem, PostmortemStatus, TimelineEntry,
)

log = get_logger(__name__)


def _id() -> str:
    return f"PM-{uuid.uuid4().hex[:8]}"


class PostmortemService:
    def __init__(self, persistence=None) -> None:
        self._items: dict[str, Postmortem] = {}
        self._p = persistence

    async def load(self) -> None:
        if self._p is None:
            return
        for pid, doc in (await self._p.load()).items():
            self._items[pid] = Postmortem(**doc)

    async def _persist(self, pm: Postmortem) -> None:
        if self._p is not None:
            await self._p.save(pm.id, pm.status.value, pm.incident_id,
                               pm.created_at.isoformat(),
                               pm.model_dump(mode="json"))

    def list(self, status: PostmortemStatus | None = None,
             incident_id: str | None = None) -> list[Postmortem]:
        out = list(self._items.values())
        if status:
            out = [p for p in out if p.status == status]
        if incident_id:
            out = [p for p in out if p.incident_id == incident_id]
        return sorted(out, key=lambda p: p.created_at, reverse=True)

    def get(self, pm_id: str) -> Postmortem | None:
        return self._items.get(pm_id)

    async def create(self, pm: Postmortem) -> Postmortem:
        if not pm.id:
            pm = pm.model_copy(update={"id": _id()})
        self._items[pm.id] = pm
        await self._persist(pm)
        log.info("Postmortem created: %s", pm.id)
        return pm

    async def update(self, pm_id: str, patch: dict) -> Postmortem | None:
        pm = self._items.get(pm_id)
        if pm is None:
            return None
        updated = pm.model_copy(update={
            **patch, "updated_at": datetime.now(timezone.utc)})
        self._items[pm_id] = updated
        await self._persist(updated)
        return updated

    async def add_timeline(self, pm_id: str, text: str, author: str,
                           at: datetime | None = None) -> Postmortem | None:
        pm = self._items.get(pm_id)
        if pm is None:
            return None
        entry = TimelineEntry(at=at or datetime.now(timezone.utc),
                              text=text, author=author)
        timeline = sorted([*pm.timeline, entry], key=lambda e: e.at)
        return await self.update(pm_id, {"timeline": timeline})

    async def add_action(self, pm_id: str, description: str, owner: str = "",
                         due: str | None = None) -> Postmortem | None:
        pm = self._items.get(pm_id)
        if pm is None:
            return None
        action = ActionItem(id=f"AI-{uuid.uuid4().hex[:6]}",
                            description=description, owner=owner, due=due)
        return await self.update(pm_id, {"action_items": [*pm.action_items, action]})

    async def complete_action(self, pm_id: str, action_id: str) -> Postmortem | None:
        pm = self._items.get(pm_id)
        if pm is None:
            return None
        items = [a.model_copy(update={"done": True}) if a.id == action_id else a
                 for a in pm.action_items]
        return await self.update(pm_id, {"action_items": items})

    async def publish(self, pm_id: str) -> Postmortem | None:
        return await self.update(pm_id, {"status": PostmortemStatus.PUBLISHED})

    def export_markdown(self, pm_id: str) -> str | None:
        pm = self._items.get(pm_id)
        if pm is None:
            return None
        lines = [
            f"# Postmortem: {pm.title}",
            f"_Status: {pm.status.value} · Severity: {pm.severity or 'n/a'}_",
            "", "## Summary", pm.summary or "_(none)_",
            "", "## Root cause", pm.root_cause or "_(none)_",
            "", "## Impact", pm.impact or "_(none)_",
            "", "## Lessons learned", pm.lessons or "_(none)_",
            "", "## Timeline",
        ]
        for e in pm.timeline:
            lines.append(f"- {e.at.isoformat()} — {e.text} ({e.author})")
        lines.append("")
        lines.append("## Action items")
        for a in pm.action_items:
            mark = "x" if a.done else " "
            lines.append(f"- [{mark}] {a.description} — {a.owner or 'unassigned'}")
        return "\n".join(lines)
