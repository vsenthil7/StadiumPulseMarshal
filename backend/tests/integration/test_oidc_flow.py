"""Production-grade OIDC: full signed flow through a mock IdP + negatives.

A self-contained mock identity provider (RSA keypair, discovery doc, JWKS, token
endpoint) served via an httpx MockTransport, so we exercise real RS256 signature
verification without a network IdP.
"""
from __future__ import annotations

import base64
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.services.oidc_service import OIDCError, OIDCService

ISSUER = "https://idp.test"
CLIENT_ID = "stadiumpulse"
REDIRECT = "https://app.test/cb"


def _b64url_uint(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class MockIdP:
    """Holds an RSA keypair and serves discovery/jwks/token for one auth code."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "test-key-1"
        self._pending: dict[str, dict] = {}  # code -> claims

    # The private key PEM PyJWT can sign with.
    @property
    def private_pem(self) -> bytes:
        from cryptography.hazmat.primitives import serialization

        return self.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def jwks(self) -> dict:
        pub = self.key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": self.kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": _b64url_uint(pub.n),
                    "e": _b64url_uint(pub.e),
                }
            ]
        }

    def make_id_token(self, claims: dict, *, sign: bool = True,
                      kid: str | None = None, wrong_key: bool = False) -> str:
        now = int(time.time())
        payload = {
            "iss": ISSUER, "aud": CLIENT_ID,
            "iat": now, "exp": now + 600, "sub": "u-1",
            **claims,
        }
        key = self.private_pem
        if wrong_key:
            other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            from cryptography.hazmat.primitives import serialization

            key = other.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        return jwt.encode(payload, key, algorithm="RS256",
                          headers={"kid": kid or self.kid})

    def stage_code(self, code: str, id_token: str) -> None:
        self._pending[code] = {"id_token": id_token}

    def transport(self) -> httpx.MockTransport:
        def handler(req: httpx.Request) -> httpx.Response:
            url = str(req.url)
            if url.endswith("/.well-known/openid-configuration"):
                return httpx.Response(200, json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/jwks",
                })
            if url.endswith("/jwks"):
                return httpx.Response(200, json=self.jwks())
            if url.endswith("/token"):
                body = dict(httpx.QueryParams(req.content.decode()))
                code = body.get("code", "")
                staged = self._pending.get(code)
                if not staged:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={
                    "access_token": "at", "token_type": "Bearer",
                    "id_token": staged["id_token"],
                })
            return httpx.Response(404)
        return httpx.MockTransport(handler)


def _service(verify: bool = True) -> OIDCService:
    return OIDCService(Settings(
        oidc_issuer=ISSUER, oidc_client_id=CLIENT_ID, oidc_redirect_uri=REDIRECT,
        jwt_secret="sek", oidc_verify_signature=verify,
    ))


# PyJWKClient does its own urllib fetch of the JWKS; point it at our JWKS by
# monkeypatching the client to use the mock transport's JWKS directly.
@pytest.fixture
def idp():
    return MockIdP()


async def _run_exchange(svc: OIDCService, idp: MockIdP, code: str, nonce: str = ""):
    client = httpx.AsyncClient(transport=idp.transport())
    # Patch signing-key lookup to use the mock JWKS (avoids real network in
    # PyJWKClient). We resolve the key from the token header kid against our JWKS.
    import app.services.oidc_service as mod

    class _FakeJWKClient:
        def __init__(self, uri): ...
        def get_signing_key_from_jwt(self, token):
            from jwt import PyJWK
            jwks = idp.jwks()
            return PyJWK.from_dict(jwks["keys"][0])

    orig = getattr(mod, "PyJWKClient", None)
    try:
        import jwt as _jwtmod
        _jwtmod.PyJWKClient = _FakeJWKClient  # type: ignore
        return await svc.exchange_code(code, expected_nonce=nonce, client=client)
    finally:
        if orig is not None:
            _jwtmod.PyJWKClient = orig  # type: ignore
        await client.aclose()


@pytest.mark.asyncio
async def test_full_flow_valid_signed_token(idp):
    svc = _service(verify=True)
    token = idp.make_id_token({"sub": "u1", "email": "a@b.com", "name": "A",
                               "roles": ["responder"], "venues": ["venue_arena_north"],
                               "nonce": "N1"})
    idp.stage_code("good", token)
    ident = await _run_exchange(svc, idp, "good", nonce="N1")
    assert ident.subject == "u1"
    assert [r.value for r in ident.roles] == ["responder"]
    assert ident.venues == ["venue_arena_north"]


@pytest.mark.asyncio
async def test_bad_signature_rejected(idp):
    svc = _service(verify=True)
    token = idp.make_id_token({"roles": ["admin"], "nonce": "N1"}, wrong_key=True)
    idp.stage_code("badsig", token)
    with pytest.raises((UnauthorizedError, OIDCError, Exception)):
        await _run_exchange(svc, idp, "badsig", nonce="N1")


@pytest.mark.asyncio
async def test_wrong_audience_rejected(idp):
    svc = _service(verify=True)
    token = idp.make_id_token({"aud": "someone-else", "roles": ["viewer"], "nonce": "N1"})
    idp.stage_code("wrongaud", token)
    with pytest.raises(Exception):
        await _run_exchange(svc, idp, "wrongaud", nonce="N1")


@pytest.mark.asyncio
async def test_expired_token_rejected(idp):
    svc = _service(verify=True)
    now = int(time.time())
    # build an already-expired token
    token = jwt.encode(
        {"iss": ISSUER, "aud": CLIENT_ID, "iat": now - 1200, "exp": now - 600,
         "sub": "u", "roles": ["viewer"], "nonce": "N1"},
        idp.private_pem, algorithm="RS256", headers={"kid": idp.kid},
    )
    idp.stage_code("expired", token)
    with pytest.raises(Exception):
        await _run_exchange(svc, idp, "expired", nonce="N1")


@pytest.mark.asyncio
async def test_nonce_mismatch_rejected(idp):
    svc = _service(verify=True)
    token = idp.make_id_token({"roles": ["viewer"], "nonce": "WRONG"})
    idp.stage_code("nonce", token)
    with pytest.raises(UnauthorizedError):
        await _run_exchange(svc, idp, "nonce", nonce="EXPECTED")


@pytest.mark.asyncio
async def test_unverified_mode_allows_unsigned_demo(idp):
    # demo mode: signature not verified, but nonce still checked
    svc = _service(verify=False)
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": "z", "roles": ["operator"], "nonce": "N1"}).encode()
    ).decode().rstrip("=")
    idp.stage_code("demo", f"{header}.{body}.")
    ident = await _run_exchange(svc, idp, "demo", nonce="N1")
    assert [r.value for r in ident.roles] == ["operator"]
