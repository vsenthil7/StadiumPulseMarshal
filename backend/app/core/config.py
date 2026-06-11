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


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (overridable in tests via cache clear)."""
    return Settings()
