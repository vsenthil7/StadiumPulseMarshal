"""Slack HMAC signature verification (P6.M6 hardening)."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.slack_signing import verify_slack_signature, sign_slack_request


# ── unit: verifier ───────────────────────────────────────────────────────────
def test_no_secret_skips_verification():
    assert verify_slack_signature(
        signing_secret=None, timestamp=None, signature=None, raw_body=b"x") is True


def test_valid_signature_passes():
    secret = "shh"
    ts = str(int(time.time()))
    body = b"text=status"
    sig = sign_slack_request(secret, ts, body)
    assert verify_slack_signature(
        signing_secret=secret, timestamp=ts, signature=sig, raw_body=body) is True


def test_tampered_body_fails():
    secret = "shh"
    ts = str(int(time.time()))
    sig = sign_slack_request(secret, ts, b"text=status")
    assert verify_slack_signature(
        signing_secret=secret, timestamp=ts, signature=sig,
        raw_body=b"text=runbook RB-x execute") is False


def test_stale_timestamp_fails():
    secret = "shh"
    ts = str(int(time.time()) - 10_000)
    sig = sign_slack_request(secret, ts, b"text=status")
    assert verify_slack_signature(
        signing_secret=secret, timestamp=ts, signature=sig,
        raw_body=b"text=status", max_age_seconds=300) is False


def test_missing_headers_fail_when_secret_set():
    assert verify_slack_signature(
        signing_secret="shh", timestamp=None, signature=None,
        raw_body=b"x") is False


def test_wrong_secret_fails():
    ts = str(int(time.time()))
    body = b"text=status"
    sig = sign_slack_request("right", ts, body)
    assert verify_slack_signature(
        signing_secret="wrong", timestamp=ts, signature=sig, raw_body=body) is False


# ── integration: route enforcement ───────────────────────────────────────────
def test_route_open_without_secret():
    with TestClient(create_app()) as c:
        r = c.post("/api/v1/chatops/slack/command", data={"text": "status"})
        assert r.status_code == 200


def test_route_rejects_unsigned_when_secret_set():
    with TestClient(create_app()) as c:
        c.app.state.ctx.settings.slack_signing_secret = "topsecret"
        try:
            r = c.post("/api/v1/chatops/slack/command", data={"text": "status"})
            assert r.status_code == 401
        finally:
            c.app.state.ctx.settings.slack_signing_secret = None


def test_route_accepts_signed_when_secret_set():
    with TestClient(create_app()) as c:
        c.app.state.ctx.settings.slack_signing_secret = "topsecret"
        try:
            ts = str(int(time.time()))
            body = b"text=status"
            sig = sign_slack_request("topsecret", ts, body)
            r = c.post("/api/v1/chatops/slack/command", content=body,
                       headers={"X-Slack-Request-Timestamp": ts,
                                "X-Slack-Signature": sig,
                                "Content-Type": "application/x-www-form-urlencoded"})
            assert r.status_code == 200 and "Status" in r.json()["text"]
        finally:
            c.app.state.ctx.settings.slack_signing_secret = None
