"""Coverage for the OIDC HTTP endpoints when SSO is ENABLED: /login issues a
307 to the IdP authorization URL; /callback verifies state, exchanges the code,
and 307-redirects with the session token in the fragment.

The OIDCService on app.state is replaced with a stub so no real IdP HTTP occurs.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.core.config as cfg
from app.main import create_app
from app.services.oidc_service import OIDCIdentity
from app.rbac.policy import Role


class _StubOIDC:
    """Stand-in OIDCService: enabled, deterministic, no network."""
    enabled = True

    def __init__(self):
        self._identity = OIDCIdentity(
            subject="oidc-sam", email="sam@corp.example", full_name="Sam",
            roles=[Role.RESPONDER], venues=["venue_arena_north"], all_venues=False,
        )

    async def authorization_url(self, return_to="/"):
        return f"https://idp.example.com/auth?return_to={return_to}&state=signed"

    def verify_state(self, state, max_age_s=600):
        return {"r": "/dashboard", "n": "nonce-1"}

    async def exchange_code(self, code, expected_nonce=""):
        return self._identity

    def mint_session_jwt(self, identity):
        return "stub.session.jwt"


@pytest.fixture
def oidc_app(monkeypatch):
    cfg.get_settings.cache_clear()
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("OIDC_CLIENT_ID", "spm")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.com/cb")
    monkeypatch.setenv("USE_MOCKS", "true")
    app = create_app()
    try:
        with TestClient(app) as c:
            app.state._oidc = _StubOIDC()  # bypass real discovery/token HTTP
            yield c
    finally:
        cfg.get_settings.cache_clear()


def test_oidc_status_enabled(oidc_app):
    s = oidc_app.get("/api/v1/auth/oidc/status")
    assert s.status_code == 200 and s.json()["enabled"] is True


def test_oidc_login_redirects_to_idp(oidc_app):
    r = oidc_app.get("/api/v1/auth/oidc/login?return_to=/home", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://idp.example.com/auth")


def test_oidc_callback_success_redirects_with_token(oidc_app):
    r = oidc_app.get("/api/v1/auth/oidc/callback?code=abc&state=signed",
                     follow_redirects=False)
    assert r.status_code == 307
    loc = r.headers["location"]
    assert loc.startswith("/dashboard#oidc_token=")
    assert "stub.session.jwt" in loc


def test_oidc_callback_missing_params_401(oidc_app):
    r = oidc_app.get("/api/v1/auth/oidc/callback", follow_redirects=False)
    assert r.status_code == 401

