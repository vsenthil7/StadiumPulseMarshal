"""SQL-durable burn-alert ack/silence store.

Same async surface as ``HashBurnAckStore`` but persisted in the ``burn_acks``
table, so acknowledgements/silences survive process restarts (durability the
in-KV stores don't provide). Rows are keyed by (kind, field) where kind is
``ack`` or ``silence`` and field is ``"{slo_id}:{severity}"``. Expired rows are
pruned lazily on read.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import delete, select

from app.repositories.sql.database import BurnAckRow, Database


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


class SqlBurnAckStore:
    def __init__(self, db: Database, ack_ttl_seconds: float = 4 * 3600) -> None:
        self._db = db
        self._ack_ttl = ack_ttl_seconds

    async def _upsert(self, kind: str, field: str, expires_at: float | None,
                      document: dict) -> None:
        async with self._db.session() as s:
            row = await s.get(BurnAckRow, (kind, field))
            if row is None:
                s.add(BurnAckRow(kind=kind, field=field,
                                 expires_at=expires_at, document=document))
            else:
                row.expires_at = expires_at
                row.document = document
            await s.commit()

    async def _get(self, kind: str, field: str) -> dict | None:
        async with self._db.session() as s:
            row = await s.get(BurnAckRow, (kind, field))
            if row is None:
                return None
            if row.expires_at is not None and row.expires_at < time.time():
                await s.delete(row)
                await s.commit()
                return None
            return dict(row.document)

    async def _delete(self, kind: str, field: str) -> bool:
        async with self._db.session() as s:
            row = await s.get(BurnAckRow, (kind, field))
            if row is None:
                return False
            await s.delete(row)
            await s.commit()
            return True

    # --- acknowledge ---------------------------------------------------------
    async def acknowledge(self, slo_id: str, severity: str, by: str,
                          note: str = "") -> AckRecord:
        now = time.time()
        expires_at = now + self._ack_ttl if self._ack_ttl else None
        doc = {"acked_by": by, "acked_at": now, "note": note}
        await self._upsert("ack", _field(slo_id, severity), expires_at, doc)
        return AckRecord(slo_id, severity, by, now, note, expires_at)

    async def ack_for(self, slo_id: str, severity: str) -> AckRecord | None:
        doc = await self._get("ack", _field(slo_id, severity))
        if doc is None:
            return None
        return AckRecord(slo_id, severity, doc["acked_by"], doc["acked_at"],
                         doc.get("note", ""))

    async def clear_ack(self, slo_id: str, severity: str) -> bool:
        return await self._delete("ack", _field(slo_id, severity))

    # --- silence -------------------------------------------------------------
    async def silence(self, slo_id: str, severity: str, minutes: float,
                       by: str) -> SilenceRecord:
        until = time.time() + minutes * 60.0
        await self._upsert("silence", _field(slo_id, severity), until,
                           {"until": until, "by": by})
        return SilenceRecord(slo_id, severity, until, by)

    async def is_silenced(self, slo_id: str, severity: str,
                          now: float | None = None) -> bool:
        doc = await self._get("silence", _field(slo_id, severity))
        return doc is not None

    async def clear_silence(self, slo_id: str, severity: str) -> bool:
        return await self._delete("silence", _field(slo_id, severity))

    # --- summary -------------------------------------------------------------
    async def active_summary(self) -> dict:
        now = time.time()
        acks: list[dict] = []
        silences: list[dict] = []
        async with self._db.session() as s:
            # prune expired
            await s.execute(
                delete(BurnAckRow).where(
                    BurnAckRow.expires_at.is_not(None),
                    BurnAckRow.expires_at < now,
                )
            )
            await s.commit()
            rows = (await s.execute(select(BurnAckRow))).scalars().all()
        for row in rows:
            slo_id, severity = _split(row.field)
            if row.kind == "ack":
                acks.append({"slo_id": slo_id, "severity": severity,
                             "acked_by": row.document.get("acked_by", ""),
                             "acked_at": row.document.get("acked_at", 0)})
            elif row.kind == "silence":
                silences.append({"slo_id": slo_id, "severity": severity,
                                 "until": row.document.get("until", 0),
                                 "by": row.document.get("by", "")})
        return {"acks": acks, "silences": silences}
