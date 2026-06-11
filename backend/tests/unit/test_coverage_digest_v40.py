"""Coverage closeout for digest_service: composers, scheduling helpers, schedulers."""
from __future__ import annotations

import asyncio

import pytest

from app.services.digest_service import (
    compose_venue_digest,
    compose_daily_digest,
    compose_digest,
    next_run_delay,
    DailyAtScheduler,
    DigestScheduler,
    VenueFanoutScheduler,
)


class _Alert:
    def __init__(self, sev, rate, venue=None, name="checkout", slo_id="S-1"):
        self.severity = sev
        self.burn_rate = rate
        self.venue_id = venue
        self.slo_name = name
        self.slo_id = slo_id


class _Counters:
    def __init__(self, ack=0, silence=0):
        self._ack = ack
        self._silence = silence

    async def totals(self, venue_id=None):
        return {"ack": self._ack, "silence": self._silence}


class _Acks:
    def __init__(self, acks=None, silences=None):
        self._acks = acks or []
        self._silences = silences or []

    async def active_summary(self):
        return {"acks": self._acks, "silences": self._silences}


class _Ctx:
    def __init__(self, alerts=None, ack=0, silence=0, acks=None, silences=None):
        self._alerts = alerts or []
        self.burn_counters = _Counters(ack, silence)
        self.burn_acks = _Acks(acks, silences)

    async def burn_alerts(self):
        return self._alerts


@pytest.mark.asyncio
async def test_compose_venue_digest_with_hottest():
    ctx = _Ctx(
        alerts=[_Alert("page", 12.0, venue="venue_arena_north", name="pay"),
                _Alert("ticket", 3.0, venue="venue_arena_north")],
        ack=3, silence=1,
    )
    msg = await compose_venue_digest(ctx, "venue_arena_north")
    assert "arena_north" in msg
    assert "1 page, 1 ticket" in msg
    assert "Hottest: pay at 12x" in msg
    assert "suppression 25%" in msg  # 1/(3+1)


@pytest.mark.asyncio
async def test_compose_venue_digest_no_alerts_no_response():
    ctx = _Ctx(alerts=[], ack=0, silence=0)
    msg = await compose_venue_digest(ctx, "venue_olympic")
    assert "0 page, 0 ticket" in msg
    assert "suppression 0%" in msg
    assert "Hottest" not in msg


@pytest.mark.asyncio
async def test_compose_daily_digest_with_top_venues():
    ctx = _Ctx(
        alerts=[_Alert("page", 9.0, venue="venue_a"),
                _Alert("ticket", 2.0, venue="venue_a"),
                _Alert("page", 5.0, venue="venue_b"),
                _Alert("ticket", 1.0)],  # unassigned
        ack=4, silence=4,
        acks=[{"slo_id": "X"}], silences=[{"slo_id": "Y"}],
    )
    msg = await compose_daily_digest(ctx)
    assert "daily burn summary" in msg.lower()
    assert "suppression 50%" in msg  # 4/(4+4)
    assert "1 acknowledged, 1 silenced" in msg
    assert "Active alerts: 4" in msg
    assert "Top venues:" in msg and "a (2)" in msg


@pytest.mark.asyncio
async def test_compose_daily_digest_empty():
    ctx = _Ctx(alerts=[], ack=0, silence=0)
    msg = await compose_daily_digest(ctx)
    assert "suppression 0%" in msg
    assert "Active alerts: 0" in msg
    assert "Top venues:" not in msg  # no venues → no line


@pytest.mark.asyncio
async def test_compose_digest_min_severity_page_only():
    ctx = _Ctx(
        alerts=[_Alert("ticket", 2.0), _Alert("page", 15.0, name="db")],
        ack=0, silence=0,
    )
    msg = await compose_digest(ctx, window_hours=12, min_severity="page")
    assert "1 page, 0 ticket" in msg
    assert "Window: 12h, min severity: page" in msg
    assert "Hottest: db at 15x" in msg


@pytest.mark.asyncio
async def test_compose_digest_no_alerts_branch():
    ctx = _Ctx(alerts=[], ack=2, silence=6)
    msg = await compose_digest(ctx)
    assert "0 page, 0 ticket" in msg
    assert "suppression 75%" in msg  # 6/(2+6)
    assert "Hottest" not in msg


def test_next_run_delay_future_and_past():
    # midnight epoch in UTC: 2021-01-01 00:00:00 = 1609459200
    base = 1609459200.0
    # target 01:00 → 3600s ahead
    assert next_run_delay("01:00", now_epoch=base, tz="UTC") == 3600.0
    # target already passed (00:00 vs base+2h) → wraps to next day
    d = next_run_delay("00:00", now_epoch=base + 7200, tz="UTC")
    assert d == 86400.0 - 7200.0


def test_next_run_delay_bad_input_defaults_0900():
    base = 1609459200.0  # 00:00 UTC
    assert next_run_delay("not-a-time", now_epoch=base, tz="UTC") == 9 * 3600.0


def test_next_run_delay_bad_tz_falls_back():
    base = 1609459200.0
    # bad tz name → local fallback, still returns a positive delay
    d = next_run_delay("01:00", now_epoch=base, tz="Not/AZone")
    assert d > 0


@pytest.mark.asyncio
async def test_digest_scheduler_idempotent_start_stop_and_status():
    ctx = _Ctx(alerts=[])
    sched = DigestScheduler(ctx, interval_seconds=0.01)
    # next_run_epoch before first sleep is an estimate
    assert sched.next_run_epoch() is not None
    sched.start()
    sched.start()  # idempotent
    await asyncio.sleep(0.05)
    st = sched.status()
    assert st["name"] == "hourly_digest" and st["running"] is True
    await sched.stop()
    await sched.stop()  # idempotent
    assert sched.status()["running"] is False


@pytest.mark.asyncio
async def test_digest_scheduler_custom_composer_and_dispatch():
    ctx = _Ctx(alerts=[])
    seen = []

    async def composer(c):
        return "custom-msg"

    async def dispatch(m):
        seen.append(m)

    sched = DigestScheduler(ctx, 0.01, dispatch=dispatch, composer=composer)
    sched.start()
    await asyncio.sleep(0.05)
    await sched.stop()
    assert "custom-msg" in seen
    assert sched.status()["runs"] >= 1


@pytest.mark.asyncio
async def test_daily_at_scheduler_status_and_stop():
    ctx = _Ctx(alerts=[])

    async def composer(c):
        return "daily"

    sched = DailyAtScheduler(ctx, at="09:00", composer=composer, dispatch=None, tz="UTC")
    assert sched.next_run_epoch() is not None
    assert sched.status()["name"] == "daily_digest"
    sched.start()
    sched.start()  # idempotent
    await asyncio.sleep(0.02)
    await sched.stop()
    await sched.stop()
    assert sched.status()["running"] is False


class _MuteAll:
    async def is_muted(self, venue_id):
        return True


class _MuteNone:
    async def is_muted(self, venue_id):
        return False


@pytest.mark.asyncio
async def test_venue_fanout_run_once_dispatches_unmuted():
    ctx = _Ctx(alerts=[_Alert("page", 8.0, venue="venue_a")])
    sent_msgs = []

    async def dispatch(vid, recipient, msg):
        sent_msgs.append((vid, recipient, msg))

    sched = VenueFanoutScheduler(
        ctx, 0.01, {"venue_a": "#ops-a", "venue_b": "#ops-b"},
        dispatch, mute_store=_MuteNone(),
    )
    sent = await sched.run_once()
    assert set(sent) == {"venue_a", "venue_b"}
    assert len(sent_msgs) == 2


@pytest.mark.asyncio
async def test_venue_fanout_skips_muted():
    ctx = _Ctx(alerts=[])
    sched = VenueFanoutScheduler(
        ctx, 0.01, {"venue_a": "#ops-a"}, dispatch=None, mute_store=_MuteAll(),
    )
    sent = await sched.run_once()
    assert sent == []


@pytest.mark.asyncio
async def test_venue_fanout_start_stop_and_next_epoch():
    ctx = _Ctx(alerts=[])

    async def dispatch(vid, recipient, msg):
        pass

    sched = VenueFanoutScheduler(ctx, 0.01, {"venue_a": "#a"}, dispatch,
                                 mute_store=_MuteNone())
    assert sched.next_run_epoch() is not None
    sched.start()
    sched.start()
    await asyncio.sleep(0.05)
    await sched.stop()
    await sched.stop()
    assert sched.status()["running"] is False

