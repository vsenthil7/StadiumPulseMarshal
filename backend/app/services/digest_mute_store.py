"""Per-venue digest mute/snooze.

Lets operators silence a venue's digest fan-out for a window (e.g. during planned
maintenance) without disabling digests globally. Backed by a KV hash field per
venue carrying the mute expiry; expired mutes are pruned on read.
"""
from __future__ import annotations

import json
import time

from app.services.kv_backend import KVBackend

_KEY = "burn:digest:mutes"


class DigestMuteStore:
    def __init__(self, kv: KVBackend) -> None:
        self._kv = kv

    async def mute(self, venue_id: str, minutes: float, by: str) -> float:
        until = time.time() + minutes * 60.0
        await self._kv.hset(_KEY, venue_id,
                            json.dumps({"until": until, "by": by}))
        return until

    async def unmute(self, venue_id: str) -> bool:
        return await self._kv.hdel(_KEY, venue_id)

    async def is_muted(self, venue_id: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        raw = await self._kv.hget(_KEY, venue_id)
        if not raw:
            return False
        try:
            rec = json.loads(raw)
        except (ValueError, TypeError):
            return False
        if rec.get("until", 0) < now:
            await self._kv.hdel(_KEY, venue_id)
            return False
        return True

    async def active(self) -> list[dict]:
        now = time.time()
        raw = await self._kv.hgetall(_KEY)
        out: list[dict] = []
        for venue_id, val in raw.items():
            try:
                rec = json.loads(val)
            except (ValueError, TypeError):
                continue
            if rec.get("until", 0) < now:
                await self._kv.hdel(_KEY, venue_id)
                continue
            out.append({"venue_id": venue_id, "until": rec["until"],
                        "by": rec.get("by", "")})
        return out
