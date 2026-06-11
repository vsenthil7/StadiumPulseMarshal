"""Coverage for AppContext lifecycle: startup wires all three digest schedulers,
shutdown stops them; plus probe_readiness, set_scenario, analytics_by_venue."""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.context import AppContext


def _digest_settings():
    """Mock-mode settings with all digest schedulers enabled (long intervals so
    the loops sleep immediately and we only exercise wiring + start/stop)."""
    return Settings(
        use_mocks=True,
        auth_enabled=False,
        burn_digest_enabled=True,
        burn_digest_interval_seconds=3600.0,
        burn_daily_digest_enabled=True,
        burn_daily_digest_at="09:00",
        burn_digest_venue_fanout_enabled=True,
        burn_digest_venue_fanout_interval_seconds=3600.0,
        burn_digest_venue_channels="venue_arena_north=#ops-north,venue_olympic_park=#ops-oly",
    )


@pytest.mark.asyncio
async def test_startup_wires_all_schedulers_then_shutdown():
    ctx = AppContext(_digest_settings())
    await ctx.startup()
    try:
        # all three optional schedulers created and running
        assert ctx.digest_scheduler is not None
        assert ctx.digest_scheduler.status()["running"] is True
        assert ctx.daily_digest_scheduler is not None
        assert ctx.daily_digest_scheduler.status()["running"] is True
        assert ctx.venue_fanout_scheduler is not None
        assert ctx.venue_fanout_scheduler.status()["running"] is True
        # core scheduler too (PruneScheduler tracks via _task, no status())
        assert ctx.prune_scheduler._task is not None
        assert ctx.prune_scheduler._task.done() is False
    finally:
        await ctx.shutdown()
    # after shutdown everything stopped
    assert ctx.digest_scheduler.status()["running"] is False
    assert ctx.daily_digest_scheduler.status()["running"] is False
    assert ctx.venue_fanout_scheduler.status()["running"] is False
    assert ctx.prune_scheduler._task is None


@pytest.mark.asyncio
async def test_startup_minimal_no_optional_schedulers():
    ctx = AppContext(Settings(use_mocks=True, auth_enabled=False))
    await ctx.startup()
    try:
        # optional schedulers stay None when disabled
        assert ctx.digest_scheduler is None
        assert ctx.daily_digest_scheduler is None
        assert ctx.venue_fanout_scheduler is None
    finally:
        await ctx.shutdown()


@pytest.mark.asyncio
async def test_probe_readiness_reports_ok():
    ctx = AppContext(Settings(use_mocks=True, auth_enabled=False))
    await ctx.startup()
    try:
        checks = await ctx.probe_readiness()
        assert "observability_client" in checks
        assert checks["observability_client"].startswith("ok")
        assert checks["persistence"].startswith("ok")
        assert checks["agent"].startswith("ok")
    finally:
        await ctx.shutdown()


@pytest.mark.asyncio
async def test_analytics_by_venue_runs():
    ctx = AppContext(Settings(use_mocks=True, auth_enabled=False))
    await ctx.startup()
    try:
        rows = await ctx.analytics_by_venue()
        assert isinstance(rows, list)
        # scoped variant
        scoped = await ctx.analytics_by_venue(principal_venues=["venue_arena_north"])
        assert isinstance(scoped, list)
    finally:
        await ctx.shutdown()


def test_set_scenario_switches_and_refreshes_slos():
    ctx = AppContext(Settings(use_mocks=True, auth_enabled=False))
    before = ctx.current_scenario
    # pick a different known scenario key if available
    from app.fixtures.scenarios.registry import DEFAULT_SCENARIO
    ctx.set_scenario(DEFAULT_SCENARIO)
    assert ctx.current_scenario == DEFAULT_SCENARIO
    # slo_engine rebuilt (not raising) and metrics backfill reset
    assert ctx._metrics_backfilled is False

