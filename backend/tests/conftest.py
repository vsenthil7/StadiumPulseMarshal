"""Shared pytest fixtures."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.context import AppContext
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(use_mocks=True)


@pytest.fixture
def context(settings: Settings) -> AppContext:
    return AppContext(settings)


@pytest.fixture
def client():
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield c
