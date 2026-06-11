"""Burn-alert acknowledge / silence workflow state.

Lets responders acknowledge a burn alert (recording who/when) and silence it for
a period so a sustained burn that's already being worked doesn't keep paging.
State is keyed by ``(slo_id, severity)``; silences expire automatically.

In-memory (suits the demo / single process); the interface is small enough to
back with Redis/SQL for multi-instance, like the other stores.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class AckRecord:
    slo_id: str
    severity: str
    acked_by: str
    acked_at: float
    note: str = ""


@dataclass
class SilenceRecord:
    slo_id: str
    severity: str
    until: float
    by: str


def _key(slo_id: str, severity: str) -> str:
    return f"{slo_id}:{severity}"


class BurnAckStore:
    def __init__(self) -> None:
        self._acks: dict[str, AckRecord] = {}
        self._silences: dict[str, SilenceRecord] = {}

    # --- acknowledge ---------------------------------------------------------
    def acknowledge(self, slo_id: str, severity: str, by: str, note: str = "") -> AckRecord:
        rec = AckRecord(slo_id=slo_id, severity=severity, acked_by=by,
                        acked_at=time.time(), note=note)
        self._acks[_key(slo_id, severity)] = rec
        return rec

    def ack_for(self, slo_id: str, severity: str) -> AckRecord | None:
        return self._acks.get(_key(slo_id, severity))

    def clear_ack(self, slo_id: str, severity: str) -> None:
        self._acks.pop(_key(slo_id, severity), None)

    # --- silence -------------------------------------------------------------
    def silence(self, slo_id: str, severity: str, minutes: float, by: str) -> SilenceRecord:
        rec = SilenceRecord(slo_id=slo_id, severity=severity,
                            until=time.time() + minutes * 60.0, by=by)
        self._silences[_key(slo_id, severity)] = rec
        return rec

    def is_silenced(self, slo_id: str, severity: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        rec = self._silences.get(_key(slo_id, severity))
        if rec is None:
            return False
        if rec.until < now:
            # expired
            del self._silences[_key(slo_id, severity)]
            return False
        return True

    def silence_until(self, slo_id: str, severity: str) -> float | None:
        rec = self._silences.get(_key(slo_id, severity))
        return rec.until if rec else None
