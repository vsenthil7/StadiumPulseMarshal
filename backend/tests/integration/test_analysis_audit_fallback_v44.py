"""Cover the audit-trail fallback paths in routes_analysis burn-trend / burn-stats.

These branches run only when the pre-aggregated counters are empty but the audit
log *does* contain burn ack/silence events (e.g. right after a restart with a
fresh KV). We seed audit entries directly on the app context and assert the
endpoints reconstruct counts/series from the audit trail.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PW = "MatchdayDemo123!"


def _h(c, email="sre@stadiumpulse.demo"):
    tok = c.post("/api/v1/auth/login",
                 json={"email": email, "password": PW}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


async def _seed_burn_audit(ctx):
    """Record burn ack/silence audit entries WITHOUT touching the counters,
    forcing the endpoints down the audit-fallback path."""
    now = datetime.now(timezone.utc)
    events = [
        ("burn.ack", "SLO-A:page"),
        ("burn.silence", "SLO-A:page"),
        ("burn.silence", "SLO-B:ticket"),
        ("burn.unsilence", "SLO-B:ticket"),
    ]
    for action, target in events:
        await ctx.audit.record(
            actor="sre-sam", action=action,
            resource_type="burn_alert", resource_id=target, metadata={},
        )


def test_burn_trend_audit_fallback():
    app = create_app()
    with TestClient(app) as c:
        ctx = app.state.ctx
        import asyncio
        asyncio.run(_seed_burn_audit(ctx))
        # counters are empty (no API acks performed) → audit-fallback path
        h = _h(c)
        r = c.get("/api/v1/slo/burn-trend?hours=24&buckets=8", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert len(body["buckets"]) == 8
        # at least one silence should appear somewhere in the reconstructed series
        total_sil = sum(b["silence"] for b in body["buckets"])
        assert total_sil >= 1


def test_burn_stats_audit_fallback_with_most_silenced():
    app = create_app()
    with TestClient(app) as c:
        ctx = app.state.ctx
        import asyncio
        asyncio.run(_seed_burn_audit(ctx))
        h = _h(c)
        r = c.get("/api/v1/slo/burn-stats?hours=24", headers=h)
        assert r.status_code == 200
        body = r.json()
        # counts reconstructed from audit
        assert body["counts"]["ack"] >= 1
        assert body["counts"]["silence"] >= 1
        # most_silenced is only populated on the audit-fallback branch
        assert isinstance(body["most_silenced"], list)
        assert any(t["target"] == "SLO-A:page" for t in body["most_silenced"])

