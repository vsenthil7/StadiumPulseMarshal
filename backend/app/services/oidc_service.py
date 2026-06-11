"""OIDC (OpenID Connect) authorization-code flow.

A thin, dependency-light OIDC client for enterprise SSO. It performs provider
discovery, builds the authorization-redirect URL, exchanges the code for tokens,
and maps ID-token claims to the app's role + venue scope. State is signed with
the app secret to protect the callback against CSRF.

Everything degrades gracefully: if OIDC is not configured the router reports
``enabled: false`` and login endpoints 404, so the demo password flow is
unaffected.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.rbac.policy import Role, roles_from_names

try:
    import jwt as _jwt
except Exception:  # pragma: no cover
    _jwt = None  # type: ignore


@dataclass
class OIDCProvider:
    """Resolved provider endpoints (from discovery)."""

    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str | None = None
    userinfo_endpoint: str | None = None


@dataclass
class OIDCIdentity:
    subject: str
    email: str
    full_name: str
    roles: list[Role]
    venues: list[str]
    all_venues: bool


class OIDCError(RuntimeError):
    pass


class OIDCService:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._provider: OIDCProvider | None = None

    @property
    def enabled(self) -> bool:
        return self._s.oidc_enabled

    # --- discovery -----------------------------------------------------------
    async def discover(self, client: httpx.AsyncClient | None = None) -> OIDCProvider:
        if self._provider is not None:
            return self._provider
        if not self.enabled:
            raise OIDCError("OIDC is not configured")
        url = self._s.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        owns = client is None
        client = client or httpx.AsyncClient(timeout=5.0)
        try:
            r = await client.get(url)
            r.raise_for_status()
            doc = r.json()
        finally:
            if owns:
                await client.aclose()
        self._provider = OIDCProvider(
            authorization_endpoint=doc["authorization_endpoint"],
            token_endpoint=doc["token_endpoint"],
            jwks_uri=doc.get("jwks_uri"),
            userinfo_endpoint=doc.get("userinfo_endpoint"),
        )
        return self._provider

    # --- state signing (CSRF protection) -------------------------------------
    def _secret(self) -> str:
        return self._s.jwt_secret or "stadiumpulse-oidc-state-secret"

    def make_state(self, return_to: str = "/") -> str:
        payload = {"t": int(time.time()), "r": return_to}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        sig = hmac.new(self._secret().encode(), body.encode(), hashlib.sha256).hexdigest()[:16]
        return f"{body}.{sig}"

    def verify_state(self, state: str, max_age_s: int = 600) -> dict:
        try:
            body, sig = state.rsplit(".", 1)
        except ValueError as exc:
            raise UnauthorizedError("Bad OIDC state") from exc
        expect = hmac.new(self._secret().encode(), body.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expect):
            raise UnauthorizedError("OIDC state signature mismatch")
        pad = "=" * (-len(body) % 4)
        data = json.loads(base64.urlsafe_b64decode(body + pad))
        if int(time.time()) - int(data.get("t", 0)) > max_age_s:
            raise UnauthorizedError("OIDC state expired")
        return data

    # --- authorization URL ---------------------------------------------------
    async def authorization_url(self, return_to: str = "/") -> str:
        provider = await self.discover()
        params = {
            "response_type": "code",
            "client_id": self._s.oidc_client_id,
            "redirect_uri": self._s.oidc_redirect_uri,
            "scope": " ".join(self._s.oidc_scope_list),
            "state": self.make_state(return_to),
        }
        return f"{provider.authorization_endpoint}?{urlencode(params)}"

    # --- code exchange -------------------------------------------------------
    async def exchange_code(
        self, code: str, client: httpx.AsyncClient | None = None
    ) -> OIDCIdentity:
        provider = await self.discover(client)
        owns = client is None
        client = client or httpx.AsyncClient(timeout=5.0)
        try:
            r = await client.post(
                provider.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._s.oidc_redirect_uri,
                    "client_id": self._s.oidc_client_id,
                    "client_secret": self._s.oidc_client_secret or "",
                },
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            tokens = r.json()
        finally:
            if owns:
                await client.aclose()
        id_token = tokens.get("id_token")
        if not id_token:
            raise OIDCError("No id_token in token response")
        return self.identity_from_id_token(id_token)

    # --- claims → identity ---------------------------------------------------
    def identity_from_id_token(self, id_token: str) -> OIDCIdentity:
        # Signature verification against JWKS is out of scope for the demo
        # provider; decode claims without verification but never trust them for
        # authorization beyond role/venue mapping. (A production deployment
        # verifies via the jwks_uri.)
        claims = _decode_unverified(id_token)
        return self.identity_from_claims(claims)

    def identity_from_claims(self, claims: dict) -> OIDCIdentity:
        roles_raw = claims.get(self._s.oidc_roles_claim, [])
        if isinstance(roles_raw, str):
            roles_raw = [r.strip() for r in roles_raw.split(",") if r.strip()]
        roles = roles_from_names([str(r) for r in roles_raw]) or [Role.VIEWER]

        venues_raw = claims.get(self._s.oidc_venues_claim, [])
        if isinstance(venues_raw, str):
            venues_raw = [v.strip() for v in venues_raw.split(",") if v.strip()]
        venues = [str(v) for v in venues_raw]
        all_venues = bool(claims.get("all_venues")) or (
            Role.ADMIN in roles and not venues
        )
        return OIDCIdentity(
            subject=str(claims.get("sub", claims.get("email", "oidc-user"))),
            email=str(claims.get("email", "")),
            full_name=str(claims.get("name", claims.get("email", "OIDC user"))),
            roles=roles,
            venues=venues,
            all_venues=all_venues,
        )

    def mint_session_jwt(self, identity: OIDCIdentity) -> str | None:
        """Mint the app's own session JWT from an OIDC identity.

        Reuses the same claim shape the rest of the API understands, so an OIDC
        sign-in produces an identical Principal to the demo-password flow.
        """
        if _jwt is None:
            return None
        now = int(time.time())
        payload = {
            "sub": identity.subject,
            self._s.jwt_roles_claim: [r.value for r in identity.roles],
            "venues": identity.venues,
            "all_venues": identity.all_venues,
            "name": identity.full_name,
            "email": identity.email,
            "iat": now,
            "exp": now + 8 * 3600,
        }
        secret = self._s.jwt_secret or "stadiumpulse-demo-secret-not-for-production"
        return _jwt.encode(payload, secret, algorithm="HS256")


def _decode_unverified(id_token: str) -> dict:
    parts = id_token.split(".")
    if len(parts) < 2:
        raise OIDCError("Malformed id_token")
    pad = "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(parts[1] + pad))
