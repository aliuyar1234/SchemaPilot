"""Runtime configuration and fail-closed startup guards."""

from __future__ import annotations

import os
from dataclasses import dataclass

from backend.shared_domain.errors import StartupConfigurationError

LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Minimal runtime settings used in bootstrap phases."""

    profile: str
    bind_address: str
    auth_mode: str
    require_auth_for_non_local: bool
    storage_root: str
    database_url: str
    oidc_claims_header: str = "x-schemapilot-oidc-claims"
    oidc_actor_id_claim: str = "sub"
    oidc_roles_claim: str = "roles"
    oidc_attributes_claim: str = "attributes"
    oidc_required_issuer: str | None = None
    oidc_required_audience: str | None = None

    @property
    def is_local_bind(self) -> bool:
        return self.bind_address in LOCAL_BIND_HOSTS

    def validate(self) -> None:
        if not self.is_local_bind and self.require_auth_for_non_local:
            if self.auth_mode in {"", "none", "disabled"}:
                raise StartupConfigurationError(
                    "Non-local bind requires explicit authentication configuration.",
                    details={
                        "bind_address": self.bind_address,
                        "auth_mode": self.auth_mode,
                    },
                )
        if self.auth_mode == "oidc" and not self.oidc_claims_header.strip():
            raise StartupConfigurationError(
                "OIDC mode requires a trusted claims header configuration.",
                details={"oidc_claims_header": self.oidc_claims_header},
            )


def load_settings() -> Settings:
    """Load settings from environment with safe defaults."""
    settings = Settings(
        profile=os.getenv("SCHEMAPILOT_PROFILE", "starter"),
        bind_address=os.getenv("SCHEMAPILOT_BIND_ADDRESS", "127.0.0.1"),
        auth_mode=os.getenv("SCHEMAPILOT_AUTH_MODE", "local"),
        require_auth_for_non_local=_parse_bool(
            os.getenv("SCHEMAPILOT_REQUIRE_AUTH_FOR_NON_LOCAL"), default=True
        ),
        storage_root=os.getenv("SCHEMAPILOT_STORAGE_ROOT", "./runtime/storage"),
        database_url=os.getenv("SCHEMAPILOT_DATABASE_URL", "sqlite:///./runtime/schemapilot.db"),
        oidc_claims_header=os.getenv("SCHEMAPILOT_OIDC_CLAIMS_HEADER", "x-schemapilot-oidc-claims"),
        oidc_actor_id_claim=os.getenv("SCHEMAPILOT_OIDC_ACTOR_ID_CLAIM", "sub"),
        oidc_roles_claim=os.getenv("SCHEMAPILOT_OIDC_ROLES_CLAIM", "roles"),
        oidc_attributes_claim=os.getenv("SCHEMAPILOT_OIDC_ATTRIBUTES_CLAIM", "attributes"),
        oidc_required_issuer=os.getenv("SCHEMAPILOT_OIDC_REQUIRED_ISSUER"),
        oidc_required_audience=os.getenv("SCHEMAPILOT_OIDC_REQUIRED_AUDIENCE"),
    )
    settings.validate()
    return settings
