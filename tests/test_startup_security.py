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


def _unsafe_trusted_proxy_settings() -> Settings:
    return Settings(
        profile="enterprise",
        bind_address="0.0.0.0",
        auth_mode="oidc_trusted_proxy",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test.db",
        oidc_claims_header="x-schemapilot-oidc-claims",
        oidc_trusted_proxy=False,
    )


def _unsafe_oidc_jwt_settings() -> Settings:
    return Settings(
        profile="enterprise",
        bind_address="0.0.0.0",
        auth_mode="oidc_jwt",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test.db",
        oidc_required_issuer=None,
        oidc_jwks_url=None,
    )


def test_control_plane_fails_on_non_local_without_auth() -> None:
    with pytest.raises(StartupConfigurationError):
        create_app(settings_factory=_unsafe_settings)


def test_gateway_fails_on_non_local_without_auth() -> None:
    with pytest.raises(StartupConfigurationError):
        create_gateway_app(settings_factory=_unsafe_settings)


def test_gateway_fails_on_non_local_trusted_proxy_without_explicit_trust() -> None:
    with pytest.raises(StartupConfigurationError):
        create_gateway_app(settings_factory=_unsafe_trusted_proxy_settings)


def test_control_plane_fails_on_non_local_trusted_proxy_without_explicit_trust() -> None:
    with pytest.raises(StartupConfigurationError):
        create_app(settings_factory=_unsafe_trusted_proxy_settings)


def test_gateway_fails_when_oidc_jwt_has_no_jwks_or_issuer() -> None:
    with pytest.raises(StartupConfigurationError):
        create_gateway_app(settings_factory=_unsafe_oidc_jwt_settings)


def test_control_plane_fails_when_oidc_jwt_has_no_jwks_or_issuer() -> None:
    with pytest.raises(StartupConfigurationError):
        create_app(settings_factory=_unsafe_oidc_jwt_settings)
