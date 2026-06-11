"""P2: Alembic migrations create all expected tables; create_all fallback works."""
from __future__ import annotations
import os
import sqlite3

import pytest


def test_alembic_upgrade_creates_tables(tmp_path):
    from alembic import command as alembic_cmd
    from alembic.config import Config as AlembicConfig

    backend_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", ".."))
    ini = os.path.join(backend_root, "alembic.ini")
    if not os.path.exists(ini):
        pytest.skip("alembic.ini not found")
    db = tmp_path / "mig.db"
    cfg = AlembicConfig(ini)
    cfg.set_main_option("script_location", os.path.join(backend_root, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    alembic_cmd.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    expected = {"incidents", "remediations", "audit", "notifications",
                "refresh_tokens", "error_budgets", "outbox", "burn_acks",
                "audit_log", "alembic_version"}
    assert expected - tables == set(), f"missing: {expected - tables}"


@pytest.mark.asyncio
async def test_database_init_schema(tmp_path):
    from app.repositories.sql.database import Database
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/init.db")
    await db.init_schema()
    await db.dispose()
    conn = sqlite3.connect(str(tmp_path / "init.db"))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "incidents" in tables and "remediations" in tables


@pytest.mark.asyncio
async def test_create_all_fallback(tmp_path):
    """create_all still works directly (the fallback path)."""
    from app.repositories.sql.database import Database
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/fb.db")
    await db.create_all()
    await db.dispose()
    conn = sqlite3.connect(str(tmp_path / "fb.db"))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "incidents" in tables
