"""Slack request signature verification (v0 HMAC scheme).

Slack signs each request with:
    sig_basestring = f"v0:{timestamp}:{raw_body}"
    signature      = "v0=" + HMAC_SHA256(signing_secret, sig_basestring).hexdigest()

sent in the headers ``X-Slack-Signature`` and ``X-Slack-Request-Timestamp``.

Verification is skipped (returns ``True``) only when no signing secret is
configured — i.e. mock/demo/CI mode. When a secret is set, requests must carry
a valid, fresh signature or they are rejected. A replay window
(``max_age_seconds``) bounds clock skew / replay.
"""
from __future__ import annotations

import hashlib
import hmac
import time


def verify_slack_signature(
    *,
    signing_secret: str | None,
    timestamp: str | None,
    signature: str | None,
    raw_body: bytes,
    max_age_seconds: int = 300,
    now: float | None = None,
) -> bool:
    # No secret configured → verification disabled (demo / CI).
    if not signing_secret:
        return True
    if not timestamp or not signature:
        return False
    # Reject stale/forward-dated requests (replay protection).
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > max_age_seconds:
        return False

    basestring = b"v0:" + timestamp.encode() + b":" + raw_body
    digest = hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    # Constant-time comparison.
    return hmac.compare_digest(expected, signature)


def sign_slack_request(signing_secret: str, timestamp: str, raw_body: bytes) -> str:
    """Helper (used in tests / outbound) to produce a valid v0 signature."""
    basestring = b"v0:" + timestamp.encode() + b":" + raw_body
    digest = hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"
