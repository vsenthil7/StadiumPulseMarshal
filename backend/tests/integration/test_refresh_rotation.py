"""OIDC/session refresh-token rotation, theft detection and revocation."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.refresh_store import RefreshStore, ReuseError

PW = "MatchdayDemo123!"


def _client() -> TestClient:
    return TestClient(create_app())


def _login(c: TestClient) -> dict:
    r = c.post("/api/v1/auth/login",
               json={"email": "operator@arena-north.demo", "password": PW})
    assert r.status_code == 200
    return r.json()


# ── store unit behaviour (async, memory-backed by default) ──────────────────
@pytest.mark.asyncio
async def test_store_rotation_issues_new_token_same_family():
    s = RefreshStore()
    t1, fam = await s.issue("alice")
    rotated = await s.rotate(t1)
    assert rotated is not None
    t2, fam2 = rotated
    assert t2 != t1
    assert fam2 == fam  # same family
    assert await s.subject_for(t2) == "alice"
    # the old token is now consumed
    assert await s.subject_for(t1) is None


@pytest.mark.asyncio
async def test_store_reuse_revokes_family():
    s = RefreshStore()
    t1, fam = await s.issue("bob")
    t2, _ = await s.rotate(t1)
    # replaying t1 (already rotated) is theft → ReuseError + family revoked
    with pytest.raises(ReuseError):
        await s.rotate(t1)
    assert await s.is_family_revoked(fam)
    # and the previously-valid t2 is now dead too
    assert await s.rotate(t2) is None
    assert await s.subject_for(t2) is None


@pytest.mark.asyncio
async def test_store_revoke_token():
    s = RefreshStore()
    t1, fam = await s.issue("carol")
    await s.revoke_token(t1)
    assert await s.is_family_revoked(fam)
    assert await s.rotate(t1) is None


@pytest.mark.asyncio
async def test_store_prune_removes_dead_records():
    s = RefreshStore()
    t1, _ = await s.issue("dave")
    t2, _ = await s.issue("erin")
    # consume t1 (rotation) and revoke t2's family → both prunable
    await s.rotate(t1)
    await s.revoke_token(t2)
    removed = await s.prune()
    assert removed >= 2


# ── endpoint behaviour ──────────────────────────────────────────────────────
def test_login_returns_refresh_token():
    with _client() as c:
        body = _login(c)
        assert body.get("refresh_token")


def test_refresh_rotation_endpoint():
    with _client() as c:
        body = _login(c)
        rt = body["refresh_token"]
        r = c.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert r.status_code == 200
        out = r.json()
        assert out["token"]
        assert out["refresh_token"] and out["refresh_token"] != rt
        # rotating the OLD token again → reuse → 401
        bad = c.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert bad.status_code == 401
        # and the rotated-to token is now also dead (family revoked)
        dead = c.post("/api/v1/auth/refresh",
                      json={"refresh_token": out["refresh_token"]})
        assert dead.status_code == 401


def test_logout_revokes_refresh_family():
    with _client() as c:
        body = _login(c)
        rt = body["refresh_token"]
        assert c.post("/api/v1/auth/logout",
                      json={"refresh_token": rt}).status_code == 200
        # after logout the refresh token can't be rotated
        assert c.post("/api/v1/auth/refresh",
                      json={"refresh_token": rt}).status_code == 401


def test_invalid_refresh_token_rejected():
    with _client() as c:
        assert c.post("/api/v1/auth/refresh",
                      json={"refresh_token": "nonsense"}).status_code == 401


# ── SQL-backed store (durability + prune) ───────────────────────────────────
@pytest.mark.asyncio
async def test_sql_backed_rotation_and_prune(tmp_path):
    from app.repositories.sql.database import Database
    from app.repositories.refresh_tokens import SQLRefreshTokenRepository

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'rt.db'}")
    await db.create_all()
    try:
        s = RefreshStore(repo=SQLRefreshTokenRepository(db))
        t1, fam = await s.issue("sql-user")
        # rotation works against SQL
        rotated = await s.rotate(t1)
        assert rotated is not None
        t2, fam2 = rotated
        assert fam2 == fam and t2 != t1
        # reuse of t1 → family revoked
        with pytest.raises(ReuseError):
            await s.rotate(t1)
        assert await s.rotate(t2) is None
        # prune clears consumed/revoked rows
        removed = await s.prune()
        assert removed >= 1
    finally:
        await db.dispose()


# ── Track E: tokens are hashed at rest ──────────────────────────────────────
@pytest.mark.asyncio
async def test_raw_token_is_not_stored():
    import hashlib
    from app.repositories.refresh_tokens import MemoryRefreshTokenRepository

    repo = MemoryRefreshTokenRepository()
    s = RefreshStore(repo=repo)
    raw, fam = await s.issue("zoe")
    # The raw token must NOT be a key in the store; only its SHA-256 hash is.
    assert await repo.get(raw) is None
    h = hashlib.sha256(raw.encode()).hexdigest()
    assert await repo.get(h) is not None
    # The store still validates the raw token presented by the client.
    assert await s.subject_for(raw) == "zoe"


@pytest.mark.asyncio
async def test_sql_hashes_token_at_rest(tmp_path):
    import hashlib
    import sqlite3
    from app.repositories.sql.database import Database
    from app.repositories.refresh_tokens import SQLRefreshTokenRepository

    dbpath = tmp_path / "rt-hash.db"
    db = Database(f"sqlite+aiosqlite:///{dbpath}")
    await db.create_all()
    try:
        s = RefreshStore(repo=SQLRefreshTokenRepository(db))
        raw, _ = await s.issue("sql-zoe")
        h = hashlib.sha256(raw.encode()).hexdigest()
    finally:
        await db.dispose()
    # Inspect the raw DB: the stored primary key is the hash, never the raw token.
    con = sqlite3.connect(dbpath)
    stored = [r[0] for r in con.execute("select token from refresh_tokens").fetchall()]
    con.close()
    assert h in stored
    assert raw not in stored
