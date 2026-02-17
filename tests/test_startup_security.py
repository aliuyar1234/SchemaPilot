from __future__ import annotations

import pytest

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.errors import StartupConfigurationError


def _unsafe_settings() -> Settings:
    return Settings(
        profile="team",
        bind_address="0.0.0.0",
        auth_mode="none",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test.db",
    )


def test_control_plane_fails_on_non_local_without_auth() -> None:
    with pytest.raises(StartupConfigurationError):
        create_app(settings_factory=_unsafe_settings)


def test_gateway_fails_on_non_local_without_auth() -> None:
    with pytest.raises(StartupConfigurationError):
        create_gateway_app(settings_factory=_unsafe_settings)
