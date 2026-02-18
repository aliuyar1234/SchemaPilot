"""Runtime configuration and fail-closed startup guards."""

from __future__ import annotations

import os
from dataclasses import dataclass

from backend.shared_domain.errors import StartupConfigurationError

LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}
SUPPORTED_AUTH_MODES = {"local", "oidc", "oidc_trusted_proxy", "oidc_jwt"}
SUPPORTED_QUERY_ENGINES = {"duckdb", "trino"}
SUPPORTED_RETRIEVAL_BACKENDS = {"filesystem", "opensearch", "qdrant"}
SUPPORTED_SECRETS_BACKENDS = {"local_encrypted", "vault"}
SUPPORTED_AUDIT_SINK_TYPES = {"disabled", "jsonl", "webhook"}
SUPPORTED_AI_PROVIDERS = {"disabled", "mock"}


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    parsed = tuple(item.strip() for item in value.split(",") if item.strip())
    return parsed or default


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
    oidc_trusted_proxy: bool = False
    oidc_required_issuer: str | None = None
    oidc_required_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_jwks_cache_ttl_seconds: int = 300
    oidc_clock_skew_seconds: int = 30
    oidc_jwt_allowed_algs: tuple[str, ...] = ("HS256",)
    retention_purge_root: str | None = None
    deletion_enabled: bool = False
    query_engine: str = "duckdb"
    trino_url: str = "http://trino:8080"
    trino_user: str = "schemapilot"
    trino_catalog: str = "memory"
    trino_schema: str = "default"
    retrieval_backend: str = "filesystem"
    opensearch_enabled: bool = False
    opensearch_url: str = "http://opensearch:9200"
    opensearch_index: str = "schemapilot_docs"
    opensearch_timeout_ms: int = 3000
    qdrant_enabled: bool = False
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "schemapilot_docs"
    qdrant_timeout_ms: int = 3000
    embeddings_provider: str = "disabled"
    embeddings_dimensions: int = 16
    query_max_bytes: int = 5_000_000
    retrieval_max_bytes: int = 2_000_000
    ai_service_enabled: bool = False
    ai_provider: str = "disabled"
    ai_gateway_url: str = "http://127.0.0.1:8001"
    ai_control_plane_url: str = "http://127.0.0.1:8000"
    secrets_store_backend: str = "local_encrypted"
    secrets_store_root: str = "./runtime/secrets"
    secrets_master_key: str | None = None
    vault_url: str | None = None
    vault_token: str | None = None
    audit_sink_type: str = "disabled"
    audit_sink_target: str | None = None
    worker_max_active_per_workspace: int = 1

    @property
    def is_local_bind(self) -> bool:
        return self.bind_address in LOCAL_BIND_HOSTS

    def validate(self) -> None:
        mode = self.auth_mode.strip().lower()
        if mode not in SUPPORTED_AUTH_MODES:
            raise StartupConfigurationError(
                "Unsupported authentication mode.",
                details={"auth_mode": self.auth_mode, "supported": sorted(SUPPORTED_AUTH_MODES)},
            )
        if not self.is_local_bind and self.require_auth_for_non_local:
            if mode in {"", "none", "disabled"}:
                raise StartupConfigurationError(
                    "Non-local bind requires explicit authentication configuration.",
                    details={
                        "bind_address": self.bind_address,
                        "auth_mode": self.auth_mode,
                    },
                )
            if mode in {"oidc", "oidc_trusted_proxy"} and not self.oidc_trusted_proxy:
                raise StartupConfigurationError(
                    "Trusted-proxy OIDC mode requires explicit trust configuration.",
                    details={
                        "auth_mode": self.auth_mode,
                        "oidc_trusted_proxy": self.oidc_trusted_proxy,
                    },
                )
        if mode in {"oidc", "oidc_trusted_proxy"} and not self.oidc_claims_header.strip():
            raise StartupConfigurationError(
                "OIDC mode requires a trusted claims header configuration.",
                details={"oidc_claims_header": self.oidc_claims_header},
            )
        if mode == "oidc_jwt":
            if not (self.oidc_jwks_url or self.oidc_required_issuer):
                raise StartupConfigurationError(
                    "OIDC JWT mode requires issuer or JWKS URL configuration.",
                    details={
                        "oidc_required_issuer": self.oidc_required_issuer,
                        "oidc_jwks_url": self.oidc_jwks_url,
                    },
                )
            if self.oidc_jwks_cache_ttl_seconds <= 0:
                raise StartupConfigurationError(
                    "OIDC JWT mode requires positive JWKS cache TTL.",
                    details={"oidc_jwks_cache_ttl_seconds": self.oidc_jwks_cache_ttl_seconds},
                )
            if self.oidc_clock_skew_seconds < 0:
                raise StartupConfigurationError(
                    "OIDC JWT mode requires non-negative clock skew.",
                    details={"oidc_clock_skew_seconds": self.oidc_clock_skew_seconds},
                )
            if not self.oidc_jwt_allowed_algs:
                raise StartupConfigurationError(
                    "OIDC JWT mode requires at least one allowed JWT algorithm.",
                    details={"oidc_jwt_allowed_algs": list(self.oidc_jwt_allowed_algs)},
                )
        if self.query_engine not in SUPPORTED_QUERY_ENGINES:
            raise StartupConfigurationError(
                "Unsupported query engine.",
                details={
                    "query_engine": self.query_engine,
                    "supported_query_engines": sorted(SUPPORTED_QUERY_ENGINES),
                },
            )
        if self.retrieval_backend not in SUPPORTED_RETRIEVAL_BACKENDS:
            raise StartupConfigurationError(
                "Unsupported retrieval backend.",
                details={
                    "retrieval_backend": self.retrieval_backend,
                    "supported_retrieval_backends": sorted(SUPPORTED_RETRIEVAL_BACKENDS),
                },
            )
        if self.opensearch_timeout_ms <= 0:
            raise StartupConfigurationError(
                "OpenSearch timeout must be positive.",
                details={"opensearch_timeout_ms": self.opensearch_timeout_ms},
            )
        if self.qdrant_timeout_ms <= 0:
            raise StartupConfigurationError(
                "Qdrant timeout must be positive.",
                details={"qdrant_timeout_ms": self.qdrant_timeout_ms},
            )
        if self.embeddings_dimensions <= 0:
            raise StartupConfigurationError(
                "Embeddings dimensions must be positive.",
                details={"embeddings_dimensions": self.embeddings_dimensions},
            )
        if self.query_max_bytes <= 0:
            raise StartupConfigurationError(
                "Query max bytes must be positive.",
                details={"query_max_bytes": self.query_max_bytes},
            )
        if self.retrieval_max_bytes <= 0:
            raise StartupConfigurationError(
                "Retrieval max bytes must be positive.",
                details={"retrieval_max_bytes": self.retrieval_max_bytes},
            )
        if self.secrets_store_backend not in SUPPORTED_SECRETS_BACKENDS:
            raise StartupConfigurationError(
                "Unsupported secrets store backend.",
                details={
                    "secrets_store_backend": self.secrets_store_backend,
                    "supported_secrets_store_backends": sorted(SUPPORTED_SECRETS_BACKENDS),
                },
            )
        if self.audit_sink_type not in SUPPORTED_AUDIT_SINK_TYPES:
            raise StartupConfigurationError(
                "Unsupported audit sink type.",
                details={
                    "audit_sink_type": self.audit_sink_type,
                    "supported_audit_sink_types": sorted(SUPPORTED_AUDIT_SINK_TYPES),
                },
            )
        if self.ai_provider not in SUPPORTED_AI_PROVIDERS:
            raise StartupConfigurationError(
                "Unsupported AI provider.",
                details={
                    "ai_provider": self.ai_provider,
                    "supported_ai_providers": sorted(SUPPORTED_AI_PROVIDERS),
                },
            )
        if self.worker_max_active_per_workspace <= 0:
            raise StartupConfigurationError(
                "Worker per-workspace active limit must be positive.",
                details={
                    "worker_max_active_per_workspace": self.worker_max_active_per_workspace
                },
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
        oidc_trusted_proxy=_parse_bool(os.getenv("SCHEMAPILOT_OIDC_TRUSTED_PROXY"), default=False),
        oidc_required_issuer=os.getenv("SCHEMAPILOT_OIDC_REQUIRED_ISSUER"),
        oidc_required_audience=os.getenv("SCHEMAPILOT_OIDC_REQUIRED_AUDIENCE"),
        oidc_jwks_url=os.getenv("SCHEMAPILOT_OIDC_JWKS_URL"),
        oidc_jwks_cache_ttl_seconds=_parse_int(
            os.getenv("SCHEMAPILOT_OIDC_JWKS_CACHE_TTL_SECONDS"), default=300
        ),
        oidc_clock_skew_seconds=_parse_int(
            os.getenv("SCHEMAPILOT_OIDC_CLOCK_SKEW_SECONDS"), default=30
        ),
        oidc_jwt_allowed_algs=_parse_csv(
            os.getenv("SCHEMAPILOT_OIDC_JWT_ALLOWED_ALGS"),
            default=("HS256",),
        ),
        retention_purge_root=os.getenv("SCHEMAPILOT_RETENTION_PURGE_ROOT"),
        deletion_enabled=_parse_bool(os.getenv("SCHEMAPILOT_DELETION_ENABLED"), default=False),
        query_engine=os.getenv("SCHEMAPILOT_QUERY_ENGINE", "duckdb").strip().lower(),
        trino_url=os.getenv("SCHEMAPILOT_TRINO_URL", "http://trino:8080"),
        trino_user=os.getenv("SCHEMAPILOT_TRINO_USER", "schemapilot"),
        trino_catalog=os.getenv("SCHEMAPILOT_TRINO_CATALOG", "memory"),
        trino_schema=os.getenv("SCHEMAPILOT_TRINO_SCHEMA", "default"),
        retrieval_backend=os.getenv("SCHEMAPILOT_RETRIEVAL_BACKEND", "filesystem")
        .strip()
        .lower(),
        opensearch_enabled=_parse_bool(
            os.getenv("SCHEMAPILOT_OPENSEARCH_ENABLED"), default=False
        ),
        opensearch_url=os.getenv("SCHEMAPILOT_OPENSEARCH_URL", "http://opensearch:9200"),
        opensearch_index=os.getenv("SCHEMAPILOT_OPENSEARCH_INDEX", "schemapilot_docs"),
        opensearch_timeout_ms=_parse_int(
            os.getenv("SCHEMAPILOT_OPENSEARCH_TIMEOUT_MS"), default=3000
        ),
        qdrant_enabled=_parse_bool(os.getenv("SCHEMAPILOT_QDRANT_ENABLED"), default=False),
        qdrant_url=os.getenv("SCHEMAPILOT_QDRANT_URL", "http://qdrant:6333"),
        qdrant_collection=os.getenv("SCHEMAPILOT_QDRANT_COLLECTION", "schemapilot_docs"),
        qdrant_timeout_ms=_parse_int(os.getenv("SCHEMAPILOT_QDRANT_TIMEOUT_MS"), default=3000),
        embeddings_provider=os.getenv("SCHEMAPILOT_EMBEDDINGS_PROVIDER", "disabled")
        .strip()
        .lower(),
        embeddings_dimensions=_parse_int(
            os.getenv("SCHEMAPILOT_EMBEDDINGS_DIMENSIONS"), default=16
        ),
        query_max_bytes=_parse_int(os.getenv("SCHEMAPILOT_QUERY_MAX_BYTES"), default=5_000_000),
        retrieval_max_bytes=_parse_int(
            os.getenv("SCHEMAPILOT_RETRIEVAL_MAX_BYTES"), default=2_000_000
        ),
        ai_service_enabled=_parse_bool(os.getenv("SCHEMAPILOT_AI_SERVICE_ENABLED"), default=False),
        ai_provider=os.getenv("SCHEMAPILOT_AI_PROVIDER", "disabled").strip().lower(),
        ai_gateway_url=os.getenv("SCHEMAPILOT_AI_GATEWAY_URL", "http://127.0.0.1:8001"),
        ai_control_plane_url=os.getenv(
            "SCHEMAPILOT_AI_CONTROL_PLANE_URL", "http://127.0.0.1:8000"
        ),
        secrets_store_backend=os.getenv("SCHEMAPILOT_SECRETS_STORE_BACKEND", "local_encrypted")
        .strip()
        .lower(),
        secrets_store_root=os.getenv("SCHEMAPILOT_SECRETS_STORE_ROOT", "./runtime/secrets"),
        secrets_master_key=os.getenv("SCHEMAPILOT_SECRETS_MASTER_KEY"),
        vault_url=os.getenv("SCHEMAPILOT_VAULT_URL"),
        vault_token=os.getenv("SCHEMAPILOT_VAULT_TOKEN"),
        audit_sink_type=os.getenv("SCHEMAPILOT_AUDIT_SINK_TYPE", "disabled").strip().lower(),
        audit_sink_target=os.getenv("SCHEMAPILOT_AUDIT_SINK_TARGET"),
        worker_max_active_per_workspace=_parse_int(
            os.getenv("SCHEMAPILOT_WORKER_MAX_ACTIVE_PER_WORKSPACE"), default=1
        ),
    )
    settings.validate()
    return settings
