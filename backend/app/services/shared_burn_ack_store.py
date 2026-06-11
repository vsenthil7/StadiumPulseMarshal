"""Shared burn-alert acknowledge / silence store (KV-backed).

The in-process ``BurnAckStore`` works for a single instance; this variant keeps
the same state in a KV backend (Memory or Redis) so acknowledge/silence applies
across replicas. To avoid needing key-scanning on the KV, all state lives in one
JSON document under a single key (read-modify-write); writes are last-wins, which
is acceptable for ack/silence (idempotent, low-contention) state.

Records:
- ack:     {acked_by, acked_at, note, expires_at}
- silence: {until, by}

Expired acks/silences are pruned on read.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app.services.kv_backend import KVBackend

_DOC_KEY = "burn:ackstate"


@dataclass
class AckRecord:
    slo_id: str
    severity: str
    acked_by: str
    acked_at: float
    note: str = ""
    expires_at: float | None = None


@dataclass
class SilenceRecord:
    slo_id: str
    severity: str
    until: float
    by: str


def _key(slo_id: str, severity: str) -> str:
    return f"{slo_id}:{severity}"


class SharedBurnAckStore:
    """KV-backed ack/silence store with the same surface as BurnAckStore, but
    async (KV I/O). ``ack_ttl_seconds`` auto-expires acknowledgements."""

    def __init__(self, kv: KVBackend, ack_ttl_seconds: float = 4 * 3600) -> None:
        self._kv = kv
        self._ack_ttl = ack_ttl_seconds

    async def _load(self) -> dict:
        raw = await self._kv.get(_DOC_KEY)
        if not raw:
            return {"acks": {}, "silences": {}}
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {"acks": {}, "silences": {}}

    async def _save(self, doc: dict) -> None:
        await self._kv.set(_DOC_KEY, json.dumps(doc))

    def _prune(self, doc: dict, now: float) -> bool:
        changed = False
        for k, rec in list(doc.get("acks", {}).items()):
            exp = rec.get("expires_at")
            if exp is not None and exp < now:
                del doc["acks"][k]
                changed = True
        for k, rec in list(doc.get("silences", {}).items()):
            if rec.get("until", 0) < now:
                del doc["silences"][k]
                changed = True
        return changed

    # --- acknowledge ---------------------------------------------------------
    async def acknowledge(self, slo_id: str, severity: str, by: str,
                          note: str = "") -> AckRecord:
        now = time.time()
        doc = await self._load()
        self._prune(doc, now)
        expires_at = now + self._ack_ttl if self._ack_ttl else None
        doc["acks"][_key(slo_id, severity)] = {
            "acked_by": by, "acked_at": now, "note": note, "expires_at": expires_at,
        }
        await self._save(doc)
        return AckRecord(slo_id, severity, by, now, note, expires_at)

    async def ack_for(self, slo_id: str, severity: str) -> AckRecord | None:
        now = time.time()
        doc = await self._load()
        if self._prune(doc, now):
            await self._save(doc)
        rec = doc.get("acks", {}).get(_key(slo_id, severity))
        if not rec:
            return None
        return AckRecord(slo_id, severity, rec["acked_by"], rec["acked_at"],
                         rec.get("note", ""), rec.get("expires_at"))

    async def clear_ack(self, slo_id: str, severity: str) -> bool:
        doc = await self._load()
        if doc.get("acks", {}).pop(_key(slo_id, severity), None) is not None:
            await self._save(doc)
            return True
        return False

    # --- silence -------------------------------------------------------------
    async def silence(self, slo_id: str, severity: str, minutes: float,
                       by: str) -> SilenceRecord:
        now = time.time()
        doc = await self._load()
        self._prune(doc, now)
        until = now + minutes * 60.0
        doc["silences"][_key(slo_id, severity)] = {"until": until, "by": by}
        await self._save(doc)
        return SilenceRecord(slo_id, severity, until, by)

    async def is_silenced(self, slo_id: str, severity: str,
                          now: float | None = None) -> bool:
        now = time.time() if now is None else now
        doc = await self._load()
        if self._prune(doc, now):
            await self._save(doc)
        return _key(slo_id, severity) in doc.get("silences", {})

    async def clear_silence(self, slo_id: str, severity: str) -> bool:
        doc = await self._load()
        if doc.get("silences", {}).pop(_key(slo_id, severity), None) is not None:
            await self._save(doc)
            return True
        return False

    async def active_summary(self) -> dict:
        """Active acks + silences (post-prune) for the on-call view."""
        now = time.time()
        doc = await self._load()
        if self._prune(doc, now):
            await self._save(doc)
        acks = [
            {"slo_id": k.rsplit(":", 1)[0], "severity": k.rsplit(":", 1)[1],
             "acked_by": v["acked_by"], "acked_at": v["acked_at"]}
            for k, v in doc.get("acks", {}).items()
        ]
        silences = [
            {"slo_id": k.rsplit(":", 1)[0], "severity": k.rsplit(":", 1)[1],
             "until": v["until"], "by": v["by"]}
            for k, v in doc.get("silences", {}).items()
        ]
        return {"acks": acks, "silences": silences}
