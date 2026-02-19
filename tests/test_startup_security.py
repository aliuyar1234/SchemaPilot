from __future__ import annotations

import pytest

from backend.ai_service.app import create_ai_service_app
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


def _unsafe_plugin_enforcement_settings() -> Settings:
    return Settings(
        profile="enterprise",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test.db",
        plugin_signing_key="",
    )


def _unsafe_ai_direct_routing_settings() -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test.db",
        ai_service_enabled=True,
        ai_provider="mock",
        ai_gateway_url="http://trino:8080",
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


def test_control_plane_fails_when_plugin_enforcement_has_no_signing_key() -> None:
    with pytest.raises(StartupConfigurationError):
        create_app(settings_factory=_unsafe_plugin_enforcement_settings)


def test_ai_service_fails_when_configured_with_direct_engine_endpoint() -> None:
    with pytest.raises(StartupConfigurationError):
        create_ai_service_app(settings_factory=_unsafe_ai_direct_routing_settings)
