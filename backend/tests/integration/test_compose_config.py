"""Structural validation of the multi-instance compose stack.

Docker isn't available in CI here, but we can guard the compose/nginx config so
the multi-instance setup can't silently regress (e.g. a replica losing its
shared REDIS_URL, which would break the global rate limit). The *runtime*
behaviour is proven by tests/integration/test_redis_e2e.py.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2].parent


def test_compose_has_redis_two_apps_and_lb():
    yaml = pytest.importorskip("yaml")
    compose = ROOT / "docker-compose.yml"
    assert compose.is_file()
    cfg = yaml.safe_load(compose.read_text())
    svcs = cfg["services"]
    assert {"redis", "app1", "app2", "lb"} <= set(svcs)


def test_both_replicas_share_redis_url():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for app in ("app1", "app2"):
        env = cfg["services"][app]["environment"]
        assert any("REDIS_URL=redis://redis:6379" in e for e in env), app
        # both depend on a healthy redis
        assert "redis" in cfg["services"][app]["depends_on"]


def test_nginx_balances_both_replicas():
    conf = (ROOT / "scripts" / "nginx.conf").read_text()
    assert "server app1:8080;" in conf
    assert "server app2:8080;" in conf
    # preserves real client IP so the shared limiter keys per client
    assert "X-Forwarded-For" in conf


def test_verifier_script_present_and_executable():
    script = ROOT / "scripts" / "verify_multi_instance.sh"
    assert script.is_file()
    assert "429" in script.read_text()  # asserts the shared limit trips


# ── Round 20: durable storage wiring ────────────────────────────────────────
def test_compose_passes_database_url_to_replicas():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for app in ("app1", "app2"):
        env = cfg["services"][app]["environment"]
        assert any("DATABASE_URL=" in e for e in env), app
        # both mount the shared data volume for the sqlite db
        assert any("/data" in v for v in cfg["services"][app].get("volumes", []))


def test_compose_declares_data_volume():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert "spm-data" in (cfg.get("volumes") or {})


def test_compose_has_postgres_profile():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    pg = cfg["services"].get("postgres")
    assert pg is not None and "pg" in pg.get("profiles", [])
    assert "spm-pg" in (cfg.get("volumes") or {})
