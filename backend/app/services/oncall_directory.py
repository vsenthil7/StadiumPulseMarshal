"""On-call directory.

Resolves *who* to notify for a given burn-alert severity, using the same on-call
roster and escalation tiers as incident escalation — so burn alerts and incident
escalations page the same people through the same channels, rather than a
hardcoded address list.

Severity → tier mapping:
- ``page``   → TIER3 (incident commander) primary, TIER2 (SRE) secondary
- ``ticket`` → TIER2 (SRE) primary, TIER1 (venue ops) secondary

Each resolved target carries the engineer's handle and their preferred channels,
so routing reflects the roster's real contact methods.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.incident import EscalationTier
from app.models.notification import NotificationChannel, OnCallEngineer

# Burn severity → ordered list of tiers to notify (primary first).
_SEVERITY_TIERS: dict[str, list[EscalationTier]] = {
    "page": [EscalationTier.TIER3, EscalationTier.TIER2],
    "ticket": [EscalationTier.TIER2, EscalationTier.TIER1],
}

_CHANNEL_BY_NAME = {c.value: c for c in NotificationChannel}


@dataclass
class OnCallTarget:
    engineer_id: str
    name: str
    tier: EscalationTier
    recipient: str
    channels: list[NotificationChannel] = field(default_factory=list)


class OnCallDirectory:
    def __init__(self, roster: list[OnCallEngineer]) -> None:
        self._by_tier: dict[EscalationTier, OnCallEngineer] = {}
        for eng in roster:
            # First engineer per tier wins (roster is ordered by precedence).
            self._by_tier.setdefault(eng.tier, eng)

    def engineer_for_tier(self, tier: EscalationTier) -> OnCallEngineer | None:
        return self._by_tier.get(tier)

    def _channels(self, eng: OnCallEngineer) -> list[NotificationChannel]:
        out: list[NotificationChannel] = []
        for name in eng.channels:
            ch = _CHANNEL_BY_NAME.get(name)
            if ch is not None:
                out.append(ch)
        return out or [NotificationChannel.EMAIL]

    def targets_for_severity(self, severity: str) -> list[OnCallTarget]:
        """Resolve the on-call targets for a burn severity, primary first.

        Falls back to any available higher tier if the mapped tier is vacant,
        so an alert is never dropped for lack of an exact-tier engineer.
        """
        tiers = _SEVERITY_TIERS.get(severity, [])
        targets: list[OnCallTarget] = []
        seen: set[str] = set()
        for tier in tiers:
            eng = self.engineer_for_tier(tier)
            if eng is None or eng.id in seen:
                continue
            seen.add(eng.id)
            targets.append(OnCallTarget(
                engineer_id=eng.id, name=eng.name, tier=eng.tier,
                recipient=eng.handle or eng.id,
                channels=self._channels(eng),
            ))
        if not targets:
            # Fallback: notify the highest tier we have anyone for.
            for tier in (EscalationTier.TIER3, EscalationTier.TIER2,
                         EscalationTier.TIER1):
                eng = self.engineer_for_tier(tier)
                if eng is not None:
                    targets.append(OnCallTarget(
                        engineer_id=eng.id, name=eng.name, tier=eng.tier,
                        recipient=eng.handle or eng.id,
                        channels=self._channels(eng),
                    ))
                    break
        return targets
