"""Application configuration.

Centralises all environment-driven settings. The ``data_source`` property is the
single source of truth for whether the app talks to live Dynatrace/Gemini or to
the bundled mock fixtures. Partial credentials are tolerated: each subsystem
falls back to mocks independently (see ``dynatrace_live`` / ``gemini_live``).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- General ---
    app_name: str = "StadiumPulse Marshal"
    app_version: str = "1.0.0"
    environment: str = Field(default="development")
    use_mocks: bool = Field(default=True, description="Force mock data path.")
    cors_origins: str = Field(default="*")

    # --- Dynatrace ---
    dt_tenant_url: str | None = None
    dt_api_token: str | None = None
    dt_mcp_url: str | None = None
    dt_mcp_client_id: str | None = None
    dt_mcp_client_secret: str | None = None

    # --- Google Cloud / Gemini ---
    google_cloud_project: str | None = None
    google_cloud_location: str = "europe-west2"
    google_api_key: str | None = None
    google_application_credentials: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # --- Behaviour ---
    auto_approve_low_risk: bool = Field(default=False)
    max_auto_approve_severity: str = Field(default="LOW")

    # --- Persistence ---
    # e.g. "sqlite+aiosqlite:///stadiumpulse.db"; empty => in-memory.
    database_url: str | None = None

    # --- Rate limiting ---
    rate_limit_enabled: bool = Field(default=False)
    rate_limit_per_minute: int = Field(default=120)
    # Stricter, always-on limit for auth endpoints (login/refresh), per client
    # IP, independent of the global limiter. Protects against credential
    # stuffing / token-guessing even when the global limiter is disabled.
    auth_rate_limit_per_minute: int = Field(default=10)
    # Optional shared backend for cross-instance rate-limiting (and future
    # shared counters). When set, auth limits are global across replicas.
    redis_url: str | None = None
    # On-call schedule source (PagerDuty/Opsgenie-shaped). When set, the current
    # on-call roster is pulled from the schedule API; else static/rotating.
    oncall_api_url: str | None = None
    oncall_api_token: str | None = None
    # Map schedule id → tier name, e.g. "SCHED_A=TIER3,SCHED_B=TIER2".
    oncall_schedule_tier_map: str = Field(default="")
    # Local rotation (when no external schedule API): rotate per-tier pools on a
    # fixed shift cadence so the on-call roster advances over time.
    oncall_rotation_enabled: bool = Field(default=True)
    oncall_shift_hours: float = Field(default=12.0)
    burn_ack_ttl_seconds: float = Field(default=4 * 3600)
    # Burn/suppression digest (periodic summary). Disabled by default.
    burn_digest_enabled: bool = Field(default=False)
    burn_digest_interval_seconds: float = Field(default=3600.0)
    burn_digest_channel: str = Field(default="slack")
    burn_digest_recipient: str = Field(default="#slo-alerts")
    burn_digest_window_hours: float = Field(default=24.0)
    burn_digest_min_severity: str = Field(default="ticket")
    burn_digest_webhook_url: str | None = None
    # Daily rollup digest (distinct from the hourly heads-up).
    burn_daily_digest_enabled: bool = Field(default=False)
    burn_daily_digest_channel: str = Field(default="slack")
    burn_daily_digest_recipient: str = Field(default="#slo-daily")
    burn_daily_digest_at: str = Field(default="09:00")
    burn_daily_digest_tz: str | None = None
    # Per-venue digest channel routing, e.g. "venue_arena_north=#north,..."
    burn_digest_venue_channels: str = Field(default="")
    burn_digest_venue_fanout_enabled: bool = Field(default=False)
    burn_digest_venue_fanout_interval_seconds: float = Field(default=3600.0)
    # Per-venue webhook URLs, e.g. "venue_arena_north=https://hooks/...,..."
    burn_digest_venue_webhooks: str = Field(default="")
    # Per-SLI metric selector overrides, e.g. "pay_avail=builtin:...,lat=builtin:..."
    metric_selector_map: str = Field(default="")
    # Security hardening toggles.
    security_headers_enabled: bool = Field(default=True)
    hsts_enabled: bool = Field(default=False)  # enable only behind TLS
    csp_override: str | None = None
    csrf_enabled: bool = Field(default=False)  # for cookie-auth deployments
    cookie_secure: bool = Field(default=False)

    # --- Webhooks ---
    webhook_timeout_seconds: float = Field(default=5.0)

    # --- Auth ---
    api_key: str | None = None
    jwt_secret: str | None = None
    auth_enabled: bool = Field(default=False)
    # Comma-separated roles granted to a valid API key (default: admin).
    api_key_roles: str = Field(default="admin")
    # JWT claim that carries a list (or comma string) of role names.
    jwt_roles_claim: str = Field(default="roles")

    # --- OIDC (optional; enables enterprise SSO sign-in) ---
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str | None = None
    # Where in the ID-token claims to find roles and venue scope.
    oidc_roles_claim: str = Field(default="roles")
    oidc_venues_claim: str = Field(default="venues")
    oidc_scopes: str = Field(default="openid profile email")
    # Strict mode (default) verifies the ID-token signature against the
    # provider JWKS and validates iss/aud/exp/nonce. Disable ONLY for a local
    # demo IdP that doesn't sign tokens.
    oidc_verify_signature: bool = Field(default=True)

    # --- Dynatrace management-zone → venue mapping ---
    # In a live tenant, venue ownership comes from a Dynatrace management zone or
    # an entity tag rather than a hardcoded id. This maps a zone/tag value to a
    # venue id. Format: "Zone A=venue_arena_north,Zone B=venue_olympic_park".
    # The entity-tag key that carries the zone name (default: "mz").
    venue_zone_map: str = Field(default="")
    venue_zone_tag_key: str = Field(default="mz")
    # Map by *management-zone id* (stable across renames). Format:
    # "12345=venue_arena_north,67890=venue_olympic_park".
    venue_zone_id_map: str = Field(default="")
    # How often (seconds) to sweep expired/consumed/revoked refresh tokens.
    refresh_prune_interval_seconds: float = Field(default=3600.0)

    @property
    def venue_zone_mapping(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.venue_zone_map.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    @property
    def venue_zone_id_mapping(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.venue_zone_id_map.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    @property
    def oncall_schedule_tier_mapping(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.oncall_schedule_tier_map.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    @property
    def metric_selector_mapping(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.metric_selector_map.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    @property
    def burn_digest_venue_channel_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.burn_digest_venue_channels.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    @property
    def burn_digest_venue_webhook_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.burn_digest_venue_webhooks.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def webhook_url_for_venue(self, venue_id: str | None) -> str | None:
        """Per-venue webhook URL if mapped, else the global digest URL."""
        if venue_id is not None:
            url = self.burn_digest_venue_webhook_map.get(venue_id)
            if url:
                return url
        return self.burn_digest_webhook_url

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_redirect_uri)

    @property
    def oidc_scope_list(self) -> list[str]:
        return [s.strip() for s in self.oidc_scopes.split() if s.strip()]

    @property
    def api_key_role_list(self) -> list[str]:
        return [r.strip() for r in self.api_key_roles.split(",") if r.strip()]

    @property
    def dynatrace_live(self) -> bool:
        """True when live Dynatrace calls are possible and not force-mocked."""
        if self.use_mocks:
            return False
        return bool(self.dt_tenant_url and self.dt_api_token)

    @property
    def gemini_live(self) -> bool:
        """True when live Gemini calls are possible and not force-mocked."""
        if self.use_mocks:
            return False
        return bool(self.google_api_key or self.google_application_credentials)

    @property
    def data_source(self) -> str:
        """Human-readable mode for the /config endpoint."""
        if self.dynatrace_live or self.gemini_live:
            return "live"
        return "mock"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_for_startup(self) -> list[str]:
        """Return a list of configuration problems (empty == OK).

        Enforces internal consistency so misconfiguration fails fast at startup
        with a clear message rather than surfacing as confusing runtime errors.
        """
        problems: list[str] = []
        if self.auth_enabled and not (self.api_key or self.jwt_secret):
            problems.append(
                "AUTH_ENABLED is true but neither API_KEY nor JWT_SECRET is set"
            )
        if self.rate_limit_enabled and self.rate_limit_per_minute <= 0:
            problems.append("RATE_LIMIT_PER_MINUTE must be > 0 when rate limiting")
        if not self.use_mocks:
            # Live mode: require at least one real backend to be configured.
            if not self.dynatrace_live and not self.gemini_live:
                problems.append(
                    "USE_MOCKS is false but no live backend is configured "
                    "(set Dynatrace or Gemini credentials, or USE_MOCKS=true)"
                )
        if self.webhook_timeout_seconds <= 0:
            problems.append("WEBHOOK_TIMEOUT_SECONDS must be > 0")
        return problems


class ConfigurationError(RuntimeError):
    """Raised at startup when settings are internally inconsistent."""


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (overridable in tests via cache clear)."""
    return Settings()
