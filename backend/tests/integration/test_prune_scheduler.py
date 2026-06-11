"""Background prune scheduler: sweeps, intervals, clean shutdown."""
from __future__ import annotations

import asyncio

import pytest

from app.services.prune_scheduler import PruneScheduler
from app.services.refresh_store import RefreshStore


@pytest.mark.asyncio
async def test_scheduler_runs_immediately_and_sweeps():
    s = RefreshStore()
    t1, _ = await s.issue("a")
    await s.rotate(t1)  # consume → prunable
    swept: list[int] = []

    async def prune():
        n = await s.prune()
        swept.append(n)
        return n

    sched = PruneScheduler(prune, interval_seconds=999, run_immediately=True)
    sched.start()
    await asyncio.sleep(0.05)
    await sched.stop()
    assert swept and swept[0] >= 1


@pytest.mark.asyncio
async def test_scheduler_repeats_on_interval():
    calls = {"n": 0}

    async def prune():
        calls["n"] += 1
        return 0

    sched = PruneScheduler(prune, interval_seconds=0.02)
    sched.start()
    await asyncio.sleep(0.1)
    await sched.stop()
    assert calls["n"] >= 2  # fired multiple times


@pytest.mark.asyncio
async def test_scheduler_start_is_idempotent_and_stops_clean():
    async def prune():
        return 0

    sched = PruneScheduler(prune, interval_seconds=999)
    sched.start()
    sched.start()  # idempotent, no second task
    await sched.stop()
    await sched.stop()  # safe to call twice


@pytest.mark.asyncio
async def test_scheduler_survives_prune_errors():
    calls = {"n": 0}

    async def prune():
        calls["n"] += 1
        raise RuntimeError("boom")

    sched = PruneScheduler(prune, interval_seconds=0.02)
    sched.start()
    await asyncio.sleep(0.08)
    await sched.stop()
    # the loop kept firing despite the prune raising
    assert calls["n"] >= 2
