"""Pre-aggregated burn-action counters.

Avoids scanning the full audit trail on every burn-stats/trend call by keeping
running counts in KV hash fields, incremented as ack/silence actions happen.

Two hashes:
- ``burn:ctr:total``  — field ``{action}`` and ``{action}:{venue}`` → count
- ``burn:ctr:bucket`` — field ``{bucketEpoch}:{action}`` → count (for the trend)

Bucket granularity is fixed (``BUCKET_SECONDS``); the trend endpoint reads the
buckets in its window. Counters are best-effort accelerators; the audit trail
remains the source of truth and the stats/trend endpoints fall back to it when
counters are empty (e.g. just after a restart with a fresh KV).
"""
from __future__ import annotations

import time

from app.services.kv_backend import KVBackend

_TOTAL = "burn:ctr:total"
_BUCKET = "burn:ctr:bucket"
BUCKET_SECONDS = 3600  # 1-hour buckets

_ACTIONS = ("ack", "silence", "unack", "unsilence")


class BurnCounters:
    def __init__(self, kv: KVBackend) -> None:
        self._kv = kv

    async def _incr_field(self, key: str, field: str, by: int = 1) -> None:
        raw = await self._kv.hget(key, field)
        cur = int(raw) if raw and raw.isdigit() else 0
        await self._kv.hset(key, field, str(cur + by))

    async def record(self, action: str, venue_id: str | None = None,
                     at: float | None = None) -> None:
        if action not in _ACTIONS:
            return
        now = at or time.time()
        await self._incr_field(_TOTAL, action)
        if venue_id:
            await self._incr_field(_TOTAL, f"{action}:{venue_id}")
        bucket = int(now // BUCKET_SECONDS) * BUCKET_SECONDS
        await self._incr_field(_BUCKET, f"{bucket}:{action}")
        if venue_id:
            await self._incr_field(_BUCKET, f"{bucket}:{action}:{venue_id}")

    async def totals(self, venue_id: str | None = None) -> dict[str, int]:
        raw = await self._kv.hgetall(_TOTAL)
        out = {a: 0 for a in _ACTIONS}
        for field, val in raw.items():
            try:
                n = int(val)
            except (ValueError, TypeError):
                continue
            parts = field.split(":")
            action = parts[0]
            field_venue = parts[1] if len(parts) > 1 else None
            if action not in out:
                continue
            if venue_id is None and field_venue is None:
                out[action] += n
            elif venue_id is not None and field_venue == venue_id:
                out[action] += n
        return out

    async def buckets(self, since_epoch: float, venue_id: str | None = None) -> dict:
        """Return {bucket_epoch: {action: count}} for buckets >= since_epoch."""
        raw = await self._kv.hgetall(_BUCKET)
        out: dict[int, dict[str, int]] = {}
        for field, val in raw.items():
            try:
                n = int(val)
            except (ValueError, TypeError):
                continue
            parts = field.split(":")
            if len(parts) < 2:
                continue
            try:
                bucket = int(parts[0])
            except ValueError:
                continue
            action = parts[1]
            field_venue = parts[2] if len(parts) > 2 else None
            if bucket < since_epoch or action not in _ACTIONS:
                continue
            if venue_id is None and field_venue is not None:
                continue
            if venue_id is not None and field_venue != venue_id:
                continue
            out.setdefault(bucket, {a: 0 for a in _ACTIONS})[action] += n
        return out

    async def any_recorded(self) -> bool:
        return bool(await self._kv.hgetall(_TOTAL))
