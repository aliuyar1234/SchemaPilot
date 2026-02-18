"""Runtime configuration and fail-closed startup guards."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.shared_domain.errors import StartupConfigurationError

LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}
SUPPORTED_AUTH_MODES = {"local", "oidc", "oidc_trusted_proxy", "oidc_jwt"}
SUPPORTED_QUERY_ENGINES = {"duckdb", "trino"}
SUPPORTED_RETRIEVAL_BACKENDS = {"filesystem", "opensearch", "qdrant"}
SUPPORTED_SECRETS_BACKENDS = {"local_encrypted", "vault"}
SUPPORTED_AUDIT_SINK_TYPES = {"disabled", "jsonl", "webhook"}
SUPPORTED_AUDIT_SINK_MODES = {"outbox", "inline"}
SUPPORTED_AI_PROVIDERS = {"disabled", "mock"}
BOOL_FIELDS = {
    "require_auth_for_non_local",
    "oidc_trusted_proxy",
    "deletion_enabled",
    "opensearch_enabled",
    "qdrant_enabled",
    "ai_service_enabled",
    "gateway_query_cache_enabled",
    "tracing_enabled",
    "plugin_network_enabled",
    "artifact_encryption_enabled",
    "materialized_refresh_enabled",
    "policy_pack_canary_enabled",
}
INT_FIELDS = {
    "oidc_jwks_cache_ttl_seconds",
    "oidc_clock_skew_seconds",
    "opensearch_timeout_ms",
    "qdrant_timeout_ms",
    "embeddings_dimensions",
    "query_max_bytes",
    "retrieval_max_bytes",
    "audit_outbox_dispatch_batch_size",
    "audit_outbox_max_attempts",
    "worker_max_active_per_workspace",
    "gateway_query_cache_ttl_seconds",
    "gateway_query_cache_max_entries",
    "worker_step_timeout_seconds",
    "worker_step_max_items",
    "plugin_max_runtime_seconds",
    "artifact_rotation_keep_previous_keys",
}
CSV_TUPLE_FIELDS = {"oidc_jwt_allowed_algs"}
LOWERCASE_FIELDS = {
    "auth_mode",
    "query_engine",
    "retrieval_backend",
    "embeddings_provider",
    "secrets_store_backend",
    "audit_sink_type",
    "audit_sink_mode",
    "ai_provider",
}
SECRET_FIELDS = {
    "secrets_master_key",
    "vault_token",
    "audit_sink_target",
}


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
    audit_sink_mode: str = "outbox"
    audit_outbox_dispatch_batch_size: int = 100
    audit_outbox_max_attempts: int = 5
    worker_max_active_per_workspace: int = 1
    gateway_query_cache_enabled: bool = False
    gateway_query_cache_ttl_seconds: int = 60
    gateway_query_cache_max_entries: int = 1024
    materialized_refresh_enabled: bool = False
    worker_step_timeout_seconds: int = 300
    worker_step_max_items: int = 10_000
    tracing_enabled: bool = False
    tracing_service_name: str = "schemapilot"
    plugin_network_enabled: bool = False
    plugin_max_runtime_seconds: int = 30
    plugin_allowed_root: str | None = None
    artifact_encryption_enabled: bool = False
    artifact_encryption_key_id: str = "v1"
    artifact_rotation_keep_previous_keys: int = 1
    policy_pack_canary_enabled: bool = False

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
        if self.audit_sink_mode not in SUPPORTED_AUDIT_SINK_MODES:
            raise StartupConfigurationError(
                "Unsupported audit sink mode.",
                details={
                    "audit_sink_mode": self.audit_sink_mode,
                    "supported_audit_sink_modes": sorted(SUPPORTED_AUDIT_SINK_MODES),
                },
            )
        if self.audit_outbox_dispatch_batch_size <= 0:
            raise StartupConfigurationError(
                "Audit outbox dispatch batch size must be positive.",
                details={"audit_outbox_dispatch_batch_size": self.audit_outbox_dispatch_batch_size},
            )
        if self.audit_outbox_max_attempts <= 0:
            raise StartupConfigurationError(
                "Audit outbox max attempts must be positive.",
                details={"audit_outbox_max_attempts": self.audit_outbox_max_attempts},
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
        if self.gateway_query_cache_ttl_seconds <= 0:
            raise StartupConfigurationError(
                "Gateway query cache TTL must be positive.",
                details={"gateway_query_cache_ttl_seconds": self.gateway_query_cache_ttl_seconds},
            )
        if self.gateway_query_cache_max_entries <= 0:
            raise StartupConfigurationError(
                "Gateway query cache max entries must be positive.",
                details={
                    "gateway_query_cache_max_entries": self.gateway_query_cache_max_entries
                },
            )
        if self.worker_step_timeout_seconds <= 0:
            raise StartupConfigurationError(
                "Worker step timeout must be positive.",
                details={"worker_step_timeout_seconds": self.worker_step_timeout_seconds},
            )
        if self.worker_step_max_items <= 0:
            raise StartupConfigurationError(
                "Worker step max items must be positive.",
                details={"worker_step_max_items": self.worker_step_max_items},
            )
        if self.plugin_max_runtime_seconds <= 0:
            raise StartupConfigurationError(
                "Plugin max runtime seconds must be positive.",
                details={"plugin_max_runtime_seconds": self.plugin_max_runtime_seconds},
            )
        if self.artifact_rotation_keep_previous_keys < 0:
            raise StartupConfigurationError(
                "Artifact rotation keep count must be non-negative.",
                details={
                    "artifact_rotation_keep_previous_keys": self.artifact_rotation_keep_previous_keys
                },
            )

    def to_redacted_dict(self) -> dict[str, object]:
        """Return sanitized settings payload safe for diagnostics/logs."""
        return redact_settings_payload(self)


def redact_settings_payload(settings: Settings) -> dict[str, object]:
    """Redact sensitive settings fields for diagnostics."""
    payload = asdict(settings)
    for key in SECRET_FIELDS:
        value = payload.get(key)
        if value is not None and str(value).strip():
            payload[key] = "<redacted>"
    database_url = str(payload.get("database_url", ""))
    payload["database_url"] = _redact_url_credentials(database_url)
    return payload


def _redact_url_credentials(value: str) -> str:
    if "://" not in value:
        return value
    scheme, rest = value.split("://", 1)
    if "@" not in rest:
        return value
    _, host = rest.rsplit("@", 1)
    return f"{scheme}://<redacted>@{host}"


def _load_config_overrides(config_path: str | None) -> dict[str, object]:
    resolved_path = _resolve_config_path(config_path)
    if resolved_path is None:
        return {}
    if not resolved_path.exists():
        raise StartupConfigurationError(
            "Configured settings file does not exist.",
            details={"config_path": resolved_path.as_posix()},
        )
    suffix = resolved_path.suffix.lower()
    if suffix in {".json"}:
        return _load_json_config_overrides(resolved_path)
    if suffix in {".yaml", ".yml"}:
        return _load_yaml_config_overrides(resolved_path)
    raise StartupConfigurationError(
        "Unsupported settings file type.",
        details={"config_path": resolved_path.as_posix(), "supported": [".json", ".yaml", ".yml"]},
    )


def _resolve_config_path(config_path: str | None) -> Path | None:
    explicit = (config_path or "").strip()
    if explicit:
        return Path(explicit)
    configured = os.getenv("SCHEMAPILOT_CONFIG_FILE", "").strip()
    if configured:
        return Path(configured)
    return None


def _load_json_config_overrides(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StartupConfigurationError(
            "Invalid JSON settings file.",
            details={"config_path": path.as_posix(), "error": str(exc)},
        ) from exc
    if not isinstance(payload, dict):
        raise StartupConfigurationError(
            "Settings file payload must be an object.",
            details={"config_path": path.as_posix()},
        )
    return {str(k): v for k, v in payload.items()}


def _load_yaml_config_overrides(path: Path) -> dict[str, object]:
    payload: dict[str, object] = {}
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise StartupConfigurationError(
                "Invalid YAML settings line.",
                details={"config_path": path.as_posix(), "line": line_no},
            )
        key, raw_value = line.split(":", 1)
        normalized_key = key.strip()
        if not normalized_key:
            raise StartupConfigurationError(
                "Invalid YAML settings key.",
                details={"config_path": path.as_posix(), "line": line_no},
            )
        payload[normalized_key] = _parse_yaml_scalar(raw_value.strip())
    return payload


def _parse_yaml_scalar(raw_value: str) -> object:
    if not raw_value:
        return ""
    lowered = raw_value.lower()
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if raw_value.startswith('"') and raw_value.endswith('"'):
        return raw_value[1:-1]
    if raw_value.startswith("'") and raw_value.endswith("'"):
        return raw_value[1:-1]
    if raw_value.startswith("[") and raw_value.endswith("]"):
        items = [part.strip() for part in raw_value[1:-1].split(",") if part.strip()]
        return [item.strip('"').strip("'") for item in items]
    if re.fullmatch(r"-?\d+", raw_value):
        return int(raw_value)
    if re.fullmatch(r"-?\d+\.\d+", raw_value):
        return float(raw_value)
    return raw_value


def _coerce_config_override(field_name: str, value: object) -> object:
    if field_name in BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return _parse_bool(value, default=False)
        raise StartupConfigurationError(
            "Invalid boolean settings override.",
            details={"field": field_name, "value": value},
        )
    if field_name in INT_FIELDS:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            parsed = _parse_int(value, default=-1)
            if parsed == -1:
                raise StartupConfigurationError(
                    "Invalid integer settings override.",
                    details={"field": field_name, "value": value},
                )
            return parsed
        raise StartupConfigurationError(
            "Invalid integer settings override.",
            details={"field": field_name, "value": value},
        )
    if field_name in CSV_TUPLE_FIELDS:
        if isinstance(value, (list, tuple)):
            parsed = tuple(str(item).strip() for item in value if str(item).strip())
            return parsed
        if isinstance(value, str):
            return _parse_csv(value, default=())
        raise StartupConfigurationError(
            "Invalid tuple settings override.",
            details={"field": field_name, "value": value},
        )
    if field_name in LOWERCASE_FIELDS:
        return str(value).strip().lower()
    if value is None:
        return None
    return str(value) if isinstance(value, (int, float, bool)) else value


def load_settings(config_path: str | None = None) -> Settings:
    """Load settings from environment with safe defaults."""
    settings_data: dict[str, Any] = {
        "profile": os.getenv("SCHEMAPILOT_PROFILE", "starter"),
        "bind_address": os.getenv("SCHEMAPILOT_BIND_ADDRESS", "127.0.0.1"),
        "auth_mode": os.getenv("SCHEMAPILOT_AUTH_MODE", "local"),
        "require_auth_for_non_local": _parse_bool(
            os.getenv("SCHEMAPILOT_REQUIRE_AUTH_FOR_NON_LOCAL"), default=True
        ),
        "storage_root": os.getenv("SCHEMAPILOT_STORAGE_ROOT", "./runtime/storage"),
        "database_url": os.getenv("SCHEMAPILOT_DATABASE_URL", "sqlite:///./runtime/schemapilot.db"),
        "oidc_claims_header": os.getenv(
            "SCHEMAPILOT_OIDC_CLAIMS_HEADER", "x-schemapilot-oidc-claims"
        ),
        "oidc_actor_id_claim": os.getenv("SCHEMAPILOT_OIDC_ACTOR_ID_CLAIM", "sub"),
        "oidc_roles_claim": os.getenv("SCHEMAPILOT_OIDC_ROLES_CLAIM", "roles"),
        "oidc_attributes_claim": os.getenv("SCHEMAPILOT_OIDC_ATTRIBUTES_CLAIM", "attributes"),
        "oidc_trusted_proxy": _parse_bool(os.getenv("SCHEMAPILOT_OIDC_TRUSTED_PROXY"), default=False),
        "oidc_required_issuer": os.getenv("SCHEMAPILOT_OIDC_REQUIRED_ISSUER"),
        "oidc_required_audience": os.getenv("SCHEMAPILOT_OIDC_REQUIRED_AUDIENCE"),
        "oidc_jwks_url": os.getenv("SCHEMAPILOT_OIDC_JWKS_URL"),
        "oidc_jwks_cache_ttl_seconds": _parse_int(
            os.getenv("SCHEMAPILOT_OIDC_JWKS_CACHE_TTL_SECONDS"), default=300
        ),
        "oidc_clock_skew_seconds": _parse_int(
            os.getenv("SCHEMAPILOT_OIDC_CLOCK_SKEW_SECONDS"), default=30
        ),
        "oidc_jwt_allowed_algs": _parse_csv(
            os.getenv("SCHEMAPILOT_OIDC_JWT_ALLOWED_ALGS"),
            default=("HS256",),
        ),
        "retention_purge_root": os.getenv("SCHEMAPILOT_RETENTION_PURGE_ROOT"),
        "deletion_enabled": _parse_bool(os.getenv("SCHEMAPILOT_DELETION_ENABLED"), default=False),
        "query_engine": os.getenv("SCHEMAPILOT_QUERY_ENGINE", "duckdb").strip().lower(),
        "trino_url": os.getenv("SCHEMAPILOT_TRINO_URL", "http://trino:8080"),
        "trino_user": os.getenv("SCHEMAPILOT_TRINO_USER", "schemapilot"),
        "trino_catalog": os.getenv("SCHEMAPILOT_TRINO_CATALOG", "memory"),
        "trino_schema": os.getenv("SCHEMAPILOT_TRINO_SCHEMA", "default"),
        "retrieval_backend": os.getenv("SCHEMAPILOT_RETRIEVAL_BACKEND", "filesystem")
        .strip()
        .lower(),
        "opensearch_enabled": _parse_bool(
            os.getenv("SCHEMAPILOT_OPENSEARCH_ENABLED"), default=False
        ),
        "opensearch_url": os.getenv("SCHEMAPILOT_OPENSEARCH_URL", "http://opensearch:9200"),
        "opensearch_index": os.getenv("SCHEMAPILOT_OPENSEARCH_INDEX", "schemapilot_docs"),
        "opensearch_timeout_ms": _parse_int(
            os.getenv("SCHEMAPILOT_OPENSEARCH_TIMEOUT_MS"), default=3000
        ),
        "qdrant_enabled": _parse_bool(os.getenv("SCHEMAPILOT_QDRANT_ENABLED"), default=False),
        "qdrant_url": os.getenv("SCHEMAPILOT_QDRANT_URL", "http://qdrant:6333"),
        "qdrant_collection": os.getenv("SCHEMAPILOT_QDRANT_COLLECTION", "schemapilot_docs"),
        "qdrant_timeout_ms": _parse_int(os.getenv("SCHEMAPILOT_QDRANT_TIMEOUT_MS"), default=3000),
        "embeddings_provider": os.getenv("SCHEMAPILOT_EMBEDDINGS_PROVIDER", "disabled")
        .strip()
        .lower(),
        "embeddings_dimensions": _parse_int(
            os.getenv("SCHEMAPILOT_EMBEDDINGS_DIMENSIONS"), default=16
        ),
        "query_max_bytes": _parse_int(os.getenv("SCHEMAPILOT_QUERY_MAX_BYTES"), default=5_000_000),
        "retrieval_max_bytes": _parse_int(
            os.getenv("SCHEMAPILOT_RETRIEVAL_MAX_BYTES"), default=2_000_000
        ),
        "ai_service_enabled": _parse_bool(os.getenv("SCHEMAPILOT_AI_SERVICE_ENABLED"), default=False),
        "ai_provider": os.getenv("SCHEMAPILOT_AI_PROVIDER", "disabled").strip().lower(),
        "ai_gateway_url": os.getenv("SCHEMAPILOT_AI_GATEWAY_URL", "http://127.0.0.1:8001"),
        "ai_control_plane_url": os.getenv(
            "SCHEMAPILOT_AI_CONTROL_PLANE_URL", "http://127.0.0.1:8000"
        ),
        "secrets_store_backend": os.getenv("SCHEMAPILOT_SECRETS_STORE_BACKEND", "local_encrypted")
        .strip()
        .lower(),
        "secrets_store_root": os.getenv("SCHEMAPILOT_SECRETS_STORE_ROOT", "./runtime/secrets"),
        "secrets_master_key": os.getenv("SCHEMAPILOT_SECRETS_MASTER_KEY"),
        "vault_url": os.getenv("SCHEMAPILOT_VAULT_URL"),
        "vault_token": os.getenv("SCHEMAPILOT_VAULT_TOKEN"),
        "audit_sink_type": os.getenv("SCHEMAPILOT_AUDIT_SINK_TYPE", "disabled").strip().lower(),
        "audit_sink_target": os.getenv("SCHEMAPILOT_AUDIT_SINK_TARGET"),
        "audit_sink_mode": os.getenv("SCHEMAPILOT_AUDIT_SINK_MODE", "outbox").strip().lower(),
        "audit_outbox_dispatch_batch_size": _parse_int(
            os.getenv("SCHEMAPILOT_AUDIT_OUTBOX_DISPATCH_BATCH_SIZE"), default=100
        ),
        "audit_outbox_max_attempts": _parse_int(
            os.getenv("SCHEMAPILOT_AUDIT_OUTBOX_MAX_ATTEMPTS"), default=5
        ),
        "worker_max_active_per_workspace": _parse_int(
            os.getenv("SCHEMAPILOT_WORKER_MAX_ACTIVE_PER_WORKSPACE"), default=1
        ),
        "gateway_query_cache_enabled": _parse_bool(
            os.getenv("SCHEMAPILOT_GATEWAY_QUERY_CACHE_ENABLED"), default=False
        ),
        "gateway_query_cache_ttl_seconds": _parse_int(
            os.getenv("SCHEMAPILOT_GATEWAY_QUERY_CACHE_TTL_SECONDS"), default=60
        ),
        "gateway_query_cache_max_entries": _parse_int(
            os.getenv("SCHEMAPILOT_GATEWAY_QUERY_CACHE_MAX_ENTRIES"), default=1024
        ),
        "materialized_refresh_enabled": _parse_bool(
            os.getenv("SCHEMAPILOT_MATERIALIZED_REFRESH_ENABLED"), default=False
        ),
        "worker_step_timeout_seconds": _parse_int(
            os.getenv("SCHEMAPILOT_WORKER_STEP_TIMEOUT_SECONDS"), default=300
        ),
        "worker_step_max_items": _parse_int(
            os.getenv("SCHEMAPILOT_WORKER_STEP_MAX_ITEMS"), default=10_000
        ),
        "tracing_enabled": _parse_bool(os.getenv("SCHEMAPILOT_TRACING_ENABLED"), default=False),
        "tracing_service_name": os.getenv("SCHEMAPILOT_TRACING_SERVICE_NAME", "schemapilot"),
        "plugin_network_enabled": _parse_bool(
            os.getenv("SCHEMAPILOT_PLUGIN_NETWORK_ENABLED"), default=False
        ),
        "plugin_max_runtime_seconds": _parse_int(
            os.getenv("SCHEMAPILOT_PLUGIN_MAX_RUNTIME_SECONDS"), default=30
        ),
        "plugin_allowed_root": os.getenv("SCHEMAPILOT_PLUGIN_ALLOWED_ROOT"),
        "artifact_encryption_enabled": _parse_bool(
            os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_ENABLED"), default=False
        ),
        "artifact_encryption_key_id": os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY_ID", "v1"),
        "artifact_rotation_keep_previous_keys": _parse_int(
            os.getenv("SCHEMAPILOT_ARTIFACT_ROTATION_KEEP_PREVIOUS_KEYS"), default=1
        ),
        "policy_pack_canary_enabled": _parse_bool(
            os.getenv("SCHEMAPILOT_POLICY_PACK_CANARY_ENABLED"), default=False
        ),
    }
    overrides = _load_config_overrides(config_path)
    known_fields = set(Settings.__dataclass_fields__.keys())
    unknown_fields = sorted(key for key in overrides if key not in known_fields)
    if unknown_fields:
        raise StartupConfigurationError(
            "Unknown settings keys are not allowed.",
            details={"unknown_keys": unknown_fields},
        )
    for key, value in overrides.items():
        settings_data[key] = _coerce_config_override(key, value)
    settings = Settings(
        **settings_data
    )
    settings.validate()
    return settings
