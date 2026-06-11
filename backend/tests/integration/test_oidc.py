"""OIDC service mapping, state signing, and status endpoint."""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.main import create_app
from app.rbac.policy import Role
from app.services.oidc_service import OIDCService


def _svc(**kw) -> OIDCService:
    base = dict(
        oidc_issuer="https://idp.example.com",
        oidc_client_id="spm",
        oidc_redirect_uri="https://app.example/cb",
        jwt_secret="testsecret",
    )
    base.update(kw)
    return OIDCService(Settings(**base))


def test_oidc_disabled_by_default():
    assert OIDCService(Settings()).enabled is False


def test_oidc_enabled_when_configured():
    assert _svc().enabled is True


def test_state_roundtrip_and_tamper():
    svc = _svc()
    st = svc.make_state("/incidents")
    data = svc.verify_state(st)
    assert data["r"] == "/incidents"
    # tampering breaks the signature
    with pytest.raises(UnauthorizedError):
        svc.verify_state(st[:-1] + ("0" if st[-1] != "0" else "1"))


def test_claims_to_identity_role_and_venue():
    svc = _svc()
    ident = svc.identity_from_claims({
        "sub": "u1", "email": "a@b.com", "name": "A B",
        "roles": ["responder"], "venues": ["venue_arena_north"],
    })
    assert ident.roles == [Role.RESPONDER]
    assert ident.venues == ["venue_arena_north"]
    assert ident.all_venues is False


def test_claims_admin_defaults_all_venues():
    svc = _svc()
    ident = svc.identity_from_claims({"sub": "u", "roles": ["admin"]})
    assert ident.all_venues is True


def test_claims_unknown_role_falls_back_to_viewer():
    svc = _svc()
    ident = svc.identity_from_claims({"sub": "u", "roles": ["wizard"]})
    assert ident.roles == [Role.VIEWER]


def test_mint_session_jwt_has_app_claims():
    svc = _svc()
    ident = svc.identity_from_claims({
        "sub": "u1", "roles": ["operator"], "venues": ["venue_x"],
    })
    token = svc.mint_session_jwt(ident)
    assert token
    payload = json.loads(
        base64.urlsafe_b64decode(token.split(".")[1] + "==")
    )
    assert payload["roles"] == ["operator"]
    assert payload["venues"] == ["venue_x"]


def test_identity_from_id_token_decodes_claims():
    svc = _svc()
    # craft an unsigned-ish JWT body
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": "z", "roles": ["viewer"]}).encode()
    ).decode().rstrip("=")
    ident = svc.identity_from_id_token(f"{header}.{body}.")
    assert ident.subject == "z"
    assert ident.roles == [Role.VIEWER]


# ── endpoint: status reflects configuration ─────────────────────────────────
def test_oidc_status_endpoint_disabled():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/auth/oidc/status")
        assert r.status_code == 200
        assert r.json()["enabled"] is False


def test_oidc_login_404s_when_disabled():
    with TestClient(create_app()) as c:
        # unconfigured → 401 (not available); never a redirect
        r = c.get("/api/v1/auth/oidc/login", follow_redirects=False)
        assert r.status_code in (401, 403)
