"""Coverage closeout for oidc_service: discovery, state signing, auth URL,
code exchange, claim mapping, session JWT, unverified decode."""
from __future__ import annotations

import base64
import json
import time

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.rbac.policy import Role
from app.services.oidc_service import (
    OIDCService, OIDCError, OIDCProvider, _decode_unverified,
)


def _settings(**kw):
    base = dict(
        oidc_issuer="https://idp.example.com",
        oidc_client_id="spm-client",
        oidc_client_secret="shh",
        oidc_redirect_uri="https://app.example.com/callback",
        oidc_verify_signature=False,
        jwt_secret="test-secret-key",
    )
    base.update(kw)
    return Settings(**base)


def _unsigned_jwt(claims: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{header}.{body}."


def test_enabled_flag():
    assert OIDCService(_settings()).enabled is True
    s = Settings(oidc_issuer=None, oidc_client_id=None, oidc_redirect_uri=None)
    assert OIDCService(s).enabled is False


@pytest.mark.asyncio
async def test_discover_fetches_and_caches():
    doc = {
        "authorization_endpoint": "https://idp.example.com/auth",
        "token_endpoint": "https://idp.example.com/token",
        "jwks_uri": "https://idp.example.com/jwks",
        "issuer": "https://idp.example.com",
    }

    def handler(request):
        assert request.url.path.endswith("/.well-known/openid-configuration")
        return httpx.Response(200, json=doc)

    svc = OIDCService(_settings())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        prov = await svc.discover(http)
        assert prov.authorization_endpoint.endswith("/auth")
        # cached → second call returns same object without HTTP
        again = await svc.discover()
        assert again is prov


@pytest.mark.asyncio
async def test_discover_raises_when_disabled():
    s = Settings(oidc_issuer=None, oidc_client_id=None, oidc_redirect_uri=None)
    with pytest.raises(OIDCError):
        await OIDCService(s).discover()


def test_state_roundtrip_and_failures():
    svc = OIDCService(_settings())
    st = svc.make_state(return_to="/dash", nonce="n1")
    data = svc.verify_state(st)
    assert data["r"] == "/dash" and data["n"] == "n1"
    # malformed (no dot)
    with pytest.raises(UnauthorizedError):
        svc.verify_state("no-dot-here")
    # tampered signature
    body, _sig = st.rsplit(".", 1)
    with pytest.raises(UnauthorizedError):
        svc.verify_state(f"{body}.deadbeefdeadbeef")
    # expired
    with pytest.raises(UnauthorizedError):
        svc.verify_state(st, max_age_s=-1)


@pytest.mark.asyncio
async def test_authorization_url_contains_params():
    doc = {
        "authorization_endpoint": "https://idp.example.com/auth",
        "token_endpoint": "https://idp.example.com/token",
    }
    svc = OIDCService(_settings())
    svc._provider = OIDCProvider(**doc)  # prime cache to skip discovery HTTP
    url = await svc.authorization_url(return_to="/home")
    assert url.startswith("https://idp.example.com/auth?")
    assert "client_id=spm-client" in url
    assert "response_type=code" in url
    assert "state=" in url and "nonce=" in url


@pytest.mark.asyncio
async def test_exchange_code_unverified_returns_identity():
    provider = OIDCProvider(
        authorization_endpoint="https://idp.example.com/auth",
        token_endpoint="https://idp.example.com/token",
        issuer="https://idp.example.com",
    )
    id_token = _unsigned_jwt({
        "sub": "u-123", "email": "sam@example.com", "name": "Sam",
        "roles": ["admin"], "nonce": "abc",
    })

    def handler(request):
        return httpx.Response(200, json={"id_token": id_token,
                                         "access_token": "at"})

    svc = OIDCService(_settings())
    svc._provider = provider
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        ident = await svc.exchange_code("the-code", expected_nonce="abc", client=http)
    assert ident.subject == "u-123"
    assert ident.email == "sam@example.com"
    assert Role.ADMIN in ident.roles
    assert ident.all_venues is True  # admin + no venues


@pytest.mark.asyncio
async def test_exchange_code_missing_id_token_raises():
    provider = OIDCProvider(
        authorization_endpoint="https://idp.example.com/auth",
        token_endpoint="https://idp.example.com/token",
    )

    def handler(request):
        return httpx.Response(200, json={"access_token": "at"})  # no id_token

    svc = OIDCService(_settings())
    svc._provider = provider
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(OIDCError):
            await svc.exchange_code("code", client=http)


def test_check_claims_nonce_and_aud_mismatch():
    svc = OIDCService(_settings())
    prov = OIDCProvider(authorization_endpoint="a", token_endpoint="t")
    # nonce mismatch
    with pytest.raises(UnauthorizedError):
        svc._check_claims({"nonce": "wrong"}, prov, "expected", verify_aud=False)
    # aud mismatch
    with pytest.raises(UnauthorizedError):
        svc._check_claims({"aud": "someone-else"}, prov, "", verify_aud=True)
    # aud as list including our client_id → ok
    svc._check_claims({"aud": ["spm-client", "x"]}, prov, "", verify_aud=True)


def test_identity_from_claims_string_roles_and_venues():
    svc = OIDCService(_settings(oidc_roles_claim="roles", oidc_venues_claim="venues"))
    ident = svc.identity_from_claims({
        "sub": "u1", "email": "a@b.com",
        "roles": "responder, viewer",
        "venues": "venue_a, venue_b",
    })
    assert ident.venues == ["venue_a", "venue_b"]
    assert ident.all_venues is False
    assert len(ident.roles) >= 1


def test_identity_from_claims_defaults_viewer():
    svc = OIDCService(_settings())
    ident = svc.identity_from_claims({"sub": "u2"})
    assert ident.roles == [Role.VIEWER]
    assert ident.email == ""


def test_identity_from_id_token():
    svc = OIDCService(_settings())
    tok = _unsigned_jwt({"sub": "u3", "email": "c@d.com", "roles": ["viewer"]})
    ident = svc.identity_from_id_token(tok)
    assert ident.subject == "u3"


def test_mint_session_jwt_roundtrip():
    import jwt as pyjwt
    svc = OIDCService(_settings())
    ident = svc.identity_from_claims({
        "sub": "u4", "email": "e@f.com", "roles": ["admin"],
    })
    token = svc.mint_session_jwt(ident)
    assert token is not None
    decoded = pyjwt.decode(token, "test-secret-key", algorithms=["HS256"])
    assert decoded["sub"] == "u4"
    assert decoded["all_venues"] is True


def test_decode_unverified_malformed_raises():
    with pytest.raises(OIDCError):
        _decode_unverified("only-one-part")

