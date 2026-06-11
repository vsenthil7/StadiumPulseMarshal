"""Slack payload, wall-clock scheduling, delivery history, per-venue routing."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.notification import NotificationChannel
from app.services.notification_service import format_webhook_payload
from app.services.digest_service import next_run_delay

PW = "MatchdayDemo123!"


def _resp(c):
    return c.post("/api/v1/auth/login",
                  json={"email": "responder@arena-north.demo", "password": PW}).json()["token"]


# ── CB: Slack payload ───────────────────────────────────────────────────────
def test_slack_payload_has_blocks():
    p = format_webhook_payload("Header line\n- a\n- b", NotificationChannel.SLACK, "#x")
    assert p["channel"] == "#x"
    assert p["blocks"][0]["type"] == "header"
    assert p["text"].startswith("Header line")


def test_non_slack_payload_is_generic():
    p = format_webhook_payload("hi", NotificationChannel.EMAIL, "a@b.com")
    assert p == {"text": "hi", "channel": "a@b.com", "source": "burn_digest"}


# ── CC: wall-clock scheduling ───────────────────────────────────────────────
def test_next_run_delay_future_today():
    # at 08:00 with target 09:00 → ~3600s
    base = _epoch_at(8, 0)
    d = next_run_delay("09:00", base)
    assert 3500 < d <= 3600


def test_next_run_delay_wraps_past_midnight():
    # at 10:00 with target 09:00 → ~23h
    base = _epoch_at(10, 0)
    d = next_run_delay("09:00", base)
    assert 82000 < d <= 86400


def _epoch_at(hh, mm):
    import time
    lt = time.localtime()
    # midnight today + hh:mm, local
    import calendar
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return midnight + hh * 3600 + mm * 60


# ── CD: delivery history status filter ──────────────────────────────────────
def test_notifications_status_filter():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        c.get("/api/v1/slo/burn-digest?dispatch=true", headers=h)
        sent = c.get("/api/v1/notifications?status=SENT", headers=h).json()["notifications"]
        assert all(n["status"] == "SENT" for n in sent)


# ── CE: per-venue digest ────────────────────────────────────────────────────
def test_venue_digest_content():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        r = c.get("/api/v1/slo/burn-digest?venue_id=venue_arena_north", headers=h)
        assert r.status_code == 200
        assert "arena_north" in r.json()["digest"]


def test_venue_digest_routes_to_mapped_channel(monkeypatch):
    import app.core.config as cfg
    cfg.get_settings.cache_clear()
    monkeypatch.setenv("BURN_DIGEST_VENUE_CHANNELS", "venue_arena_north=#north-room")
    try:
        with TestClient(create_app()) as c:
            h = {"Authorization": f"Bearer {_resp(c)}"}
            r = c.get("/api/v1/slo/burn-digest?venue_id=venue_arena_north&dispatch=true",
                      headers=h)
            assert r.status_code == 200
            assert r.json()["recipient"] == "#north-room"
    finally:
        cfg.get_settings.cache_clear()
