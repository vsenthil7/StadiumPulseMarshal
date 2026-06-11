"""Hash-backed burn-alert ack/silence store (KV-backed, multi-instance).

Each ``(slo_id, severity)`` entry lives in its own hash field, so acknowledging
one alert never rewrites another's state — there is no whole-document
last-write-wins window across fields. Acks and silences live in two hashes
(``burn:acks`` / ``burn:silences``); each field value is a small JSON blob
carrying the expiry, pruned lazily on read. Backed by any ``KVBackend`` with hash
ops (Memory or Redis), so state is shared across replicas.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app.services.kv_backend import KVBackend

_ACKS = "burn:acks"
_SILENCES = "burn:silences"


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


def _field(slo_id: str, severity: str) -> str:
    return f"{slo_id}:{severity}"


def _split(field: str) -> tuple[str, str]:
    slo_id, _, severity = field.rpartition(":")
    return slo_id, severity


class HashBurnAckStore:
    def __init__(self, kv: KVBackend, ack_ttl_seconds: float = 4 * 3600) -> None:
        self._kv = kv
        self._ack_ttl = ack_ttl_seconds

    # --- acknowledge ---------------------------------------------------------
    async def acknowledge(self, slo_id: str, severity: str, by: str,
                          note: str = "") -> AckRecord:
        now = time.time()
        expires_at = now + self._ack_ttl if self._ack_ttl else None
        payload = json.dumps({"acked_by": by, "acked_at": now, "note": note,
                              "expires_at": expires_at})
        await self._kv.hset(_ACKS, _field(slo_id, severity), payload)
        return AckRecord(slo_id, severity, by, now, note, expires_at)

    async def ack_for(self, slo_id: str, severity: str) -> AckRecord | None:
        raw = await self._kv.hget(_ACKS, _field(slo_id, severity))
        if not raw:
            return None
        try:
            rec = json.loads(raw)
        except (ValueError, TypeError):
            return None
        exp = rec.get("expires_at")
        if exp is not None and exp < time.time():
            await self._kv.hdel(_ACKS, _field(slo_id, severity))
            return None
        return AckRecord(slo_id, severity, rec["acked_by"], rec["acked_at"],
                         rec.get("note", ""), exp)

    async def clear_ack(self, slo_id: str, severity: str) -> bool:
        return await self._kv.hdel(_ACKS, _field(slo_id, severity))

    # --- silence -------------------------------------------------------------
    async def silence(self, slo_id: str, severity: str, minutes: float,
                       by: str) -> SilenceRecord:
        until = time.time() + minutes * 60.0
        await self._kv.hset(_SILENCES, _field(slo_id, severity),
                            json.dumps({"until": until, "by": by}))
        return SilenceRecord(slo_id, severity, until, by)

    async def is_silenced(self, slo_id: str, severity: str,
                          now: float | None = None) -> bool:
        now = time.time() if now is None else now
        raw = await self._kv.hget(_SILENCES, _field(slo_id, severity))
        if not raw:
            return False
        try:
            rec = json.loads(raw)
        except (ValueError, TypeError):
            return False
        if rec.get("until", 0) < now:
            await self._kv.hdel(_SILENCES, _field(slo_id, severity))
            return False
        return True

    async def clear_silence(self, slo_id: str, severity: str) -> bool:
        return await self._kv.hdel(_SILENCES, _field(slo_id, severity))

    # --- summary -------------------------------------------------------------
    async def active_summary(self) -> dict:
        now = time.time()
        both = await self._kv.hgetall_many([_ACKS, _SILENCES])
        acks_raw = both.get(_ACKS, {})
        sil_raw = both.get(_SILENCES, {})
        acks = []
        for field, raw in acks_raw.items():
            try:
                rec = json.loads(raw)
            except (ValueError, TypeError):
                continue
            exp = rec.get("expires_at")
            if exp is not None and exp < now:
                await self._kv.hdel(_ACKS, field)
                continue
            slo_id, severity = _split(field)
            acks.append({"slo_id": slo_id, "severity": severity,
                         "acked_by": rec["acked_by"], "acked_at": rec["acked_at"]})
        silences = []
        for field, raw in sil_raw.items():
            try:
                rec = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if rec.get("until", 0) < now:
                await self._kv.hdel(_SILENCES, field)
                continue
            slo_id, severity = _split(field)
            silences.append({"slo_id": slo_id, "severity": severity,
                             "until": rec["until"], "by": rec["by"]})
        return {"acks": acks, "silences": silences}
