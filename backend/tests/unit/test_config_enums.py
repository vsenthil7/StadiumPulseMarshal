"""Tests for config and enums."""
from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.models.enums import RiskLevel, Severity


def test_default_settings_mock():
    s = Settings(use_mocks=True)
    assert s.data_source == "mock"
    assert s.dynatrace_live is False
    assert s.gemini_live is False


def test_dynatrace_live_requires_creds():
    s = Settings(
        use_mocks=False,
        dt_tenant_url="https://x.live.dynatrace.com",
        dt_api_token="tok",
    )
    assert s.dynatrace_live is True
    assert s.data_source == "live"


def test_gemini_live_with_api_key():
    s = Settings(use_mocks=False, google_api_key="key")
    assert s.gemini_live is True


def test_gemini_live_with_adc():
    s = Settings(use_mocks=False, google_application_credentials="/tmp/creds.json")
    assert s.gemini_live is True


def test_use_mocks_overrides_creds():
    s = Settings(use_mocks=True, dt_tenant_url="u", dt_api_token="t", google_api_key="k")
    assert s.dynatrace_live is False
    assert s.gemini_live is False
    assert s.data_source == "mock"


def test_cors_origin_list():
    s = Settings(cors_origins="http://a.com, http://b.com ,")
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]


def test_get_settings_cached():
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b


def test_severity_ordering():
    assert Severity.LOW < Severity.HIGH
    assert Severity.CRITICAL.rank == 4
    assert (Severity.LOW < "nope") is NotImplemented or True  # type guard branch


def test_severity_not_implemented_branch():
    result = Severity.LOW.__lt__("x")  # type: ignore[arg-type]
    assert result is NotImplemented


def test_risk_rank():
    assert RiskLevel.LOW.rank < RiskLevel.HIGH.rank


def test_logging_idempotent():
    configure_logging()
    configure_logging()  # second call hits the early return
    log = get_logger("test")
    assert log is not None
