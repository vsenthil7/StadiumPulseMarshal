"""SQL-durable burn ack store: persists across store instances on one DB."""
from __future__ import annotations

import time

import pytest

from app.repositories.sql.database import Database
from app.services.sql_burn_ack_store import SqlBurnAckStore


async def _db():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_all()
    return db


@pytest.mark.asyncio
async def test_ack_persists_across_instances_same_db():
    db = await _db()
    a = SqlBurnAckStore(db)
    await a.acknowledge("SLO-X", "page", "alice", "looking")
    # a second store over the SAME db sees the ack (durability/shared)
    b = SqlBurnAckStore(db)
    rec = await b.ack_for("SLO-X", "page")
    assert rec is not None and rec.acked_by == "alice"
    await db.dispose()


@pytest.mark.asyncio
async def test_silence_and_clear():
    db = await _db()
    s = SqlBurnAckStore(db)
    await s.silence("SLO-X", "ticket", minutes=30, by="bob")
    assert await s.is_silenced("SLO-X", "ticket") is True
    assert await s.clear_silence("SLO-X", "ticket") is True
    assert await s.is_silenced("SLO-X", "ticket") is False
    await db.dispose()


@pytest.mark.asyncio
async def test_ack_expiry():
    db = await _db()
    s = SqlBurnAckStore(db, ack_ttl_seconds=0.05)
    await s.acknowledge("SLO-X", "page", "alice")
    assert await s.ack_for("SLO-X", "page") is not None
    time.sleep(0.1)
    assert await s.ack_for("SLO-X", "page") is None
    await db.dispose()


@pytest.mark.asyncio
async def test_active_summary():
    db = await _db()
    s = SqlBurnAckStore(db)
    await s.acknowledge("SLO-A", "page", "alice")
    await s.silence("SLO-B", "ticket", 30, "bob")
    summ = await s.active_summary()
    assert len(summ["acks"]) == 1 and summ["acks"][0]["slo_id"] == "SLO-A"
    assert len(summ["silences"]) == 1 and summ["silences"][0]["slo_id"] == "SLO-B"
    await db.dispose()


def test_full_app_with_database_acks_through_api(monkeypatch, tmp_path):
    """Boot the full app with DATABASE_URL set and ack via the API — confirms
    the burn_acks table is created (repos.init) before the SQL store is used."""
    import app.core.config as cfg
    cfg.get_settings.cache_clear()
    db_path = tmp_path / "spm.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("USE_MOCKS", "true")
    from fastapi.testclient import TestClient
    from app.main import create_app
    try:
        with TestClient(create_app()) as c:
            tok = c.post("/api/v1/auth/login",
                         json={"email": "responder@arena-north.demo",
                               "password": "MatchdayDemo123!"}).json()["token"]
            h = {"Authorization": f"Bearer {tok}"}
            alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
            if not alerts:
                return
            a = alerts[0]
            r = c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/ack",
                       json={"severity": a["severity"]}, headers=h)
            assert r.status_code == 200 and r.json()["acknowledged"]
            again = c.get("/api/v1/slo/burn-alerts", headers=h).json()
            assert again["acked_count"] >= 1
    finally:
        cfg.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_concurrent_writers_distinct_keys():
    """Many concurrent upserts to distinct (slo,severity) rows all persist
    (SQLite serializes writes; the store must not lose rows under gather)."""
    import asyncio
    db = await _db()
    s = SqlBurnAckStore(db)
    await asyncio.gather(*[
        s.acknowledge(f"SLO-{i}", "page", f"user{i}") for i in range(15)
    ])
    summ = await s.active_summary()
    assert len(summ["acks"]) == 15
    await db.dispose()
