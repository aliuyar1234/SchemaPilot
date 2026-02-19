"""CLI doctor preflight checks for operator readiness."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from backend.shared_domain.config import load_settings
from backend.shared_domain.db import ensure_required_revision, get_engine, get_session_factory
from backend.shared_domain.errors import StartupConfigurationError
from backend.shared_domain.metadata_models import TargetDbProfile, TargetDbState
from backend.shared_domain.secrets_store import (
    LocalEncryptedSecretsStore,
    VaultSecretsStore,
    load_secrets_store,
)

BYPASS_PORTS = (8080, 8083, 9200, 6333)
BYPASS_TOKENS = tuple(f"{port}:{port}" for port in BYPASS_PORTS)
COMPOSE_ONLY_BLOCKED_MAPPINGS = ("5432:5432",)
PORT_PATTERN = re.compile(r"\b(?:port|targetPort|nodePort)\s*:\s*(\d+)\b")

CHECK_CATEGORIES: dict[str, str] = {
    "settings.load": "configuration",
    "storage.writable": "storage",
    "database.connectivity": "database",
    "database.migrations": "database",
    "deploy.no_bypass_ports": "security",
    "auth.configuration": "security",
    "secrets.backend": "security",
    "target_db.health": "operability",
    "plugin.sandbox": "security",
    "oidc.jwks_reachability": "security",
}

CHECK_REMEDIATIONS: dict[str, str] = {
    "settings.load": "DR-0001",
    "storage.writable": "DR-0002",
    "database.connectivity": "DR-0003",
    "database.migrations": "DR-0004",
    "deploy.no_bypass_ports": "DR-0005",
    "auth.configuration": "DR-0006",
    "secrets.backend": "DR-0007",
    "target_db.health": "DR-0008",
    "plugin.sandbox": "DR-0009",
    "oidc.jwks_reachability": "DR-0010",
}


def run_doctor_preflight(*, config_path: str | None = None) -> dict[str, object]:
    """Run deterministic doctor checks and return structured report."""
    checks: list[dict[str, object]] = []
    settings = None
    settings_error = None
    try:
        settings = load_settings(config_path=config_path)
        checks.append(
            _annotate_check(
                {
                    "check_id": "settings.load",
                    "status": "pass",
                    "message": "Settings loaded and validated.",
                    "details": settings.to_redacted_dict(),
                }
            )
        )
    except StartupConfigurationError as exc:
        settings_error = exc
        checks.append(
            _annotate_check(
                {
                    "check_id": "settings.load",
                    "status": "fail",
                    "message": str(exc),
                    "details": exc.details,
                }
            )
        )
    if settings is None:
        return {
            "status": "fail",
            "checks": checks,
            "config_path": config_path or os.getenv("SCHEMAPILOT_CONFIG_FILE"),
            "error": str(settings_error) if settings_error is not None else "settings_not_loaded",
        }

    checks.append(_annotate_check(_check_storage_writable(settings.storage_root)))
    checks.append(_annotate_check(_check_database_connectivity(settings.database_url)))
    checks.append(_annotate_check(_check_migration_state(settings)))
    checks.append(_annotate_check(_check_no_bypass_ports()))
    checks.append(_annotate_check(_check_auth_configuration(settings)))
    checks.append(_annotate_check(_check_secrets_backend_availability(settings)))
    checks.append(_annotate_check(_check_target_db_health(settings)))
    checks.append(_annotate_check(_check_plugin_sandbox_settings(settings)))
    checks.append(_annotate_check(_check_jwks_reachability(settings)))
    failed = [item for item in checks if item.get("status") == "fail"]
    return {
        "status": "fail" if failed else "ok",
        "checks": checks,
        "config_path": config_path or os.getenv("SCHEMAPILOT_CONFIG_FILE"),
    }


def _annotate_check(check: dict[str, object]) -> dict[str, object]:
    check_id = str(check.get("check_id", "")).strip()
    check["category"] = CHECK_CATEGORIES.get(check_id, "operability")
    status = str(check.get("status", "")).strip().lower()
    check["remediation_id"] = CHECK_REMEDIATIONS.get(check_id) if status == "fail" else None
    return check


def _check_storage_writable(storage_root: str) -> dict[str, object]:
    root = Path(storage_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {
            "check_id": "storage.writable",
            "status": "pass",
            "message": "Storage root is writable.",
            "details": {"storage_root": root.as_posix()},
        }
    except OSError as exc:
        return {
            "check_id": "storage.writable",
            "status": "fail",
            "message": "Storage root is not writable.",
            "details": {"storage_root": root.as_posix(), "error": str(exc)},
        }


def _check_database_connectivity(database_url: str) -> dict[str, object]:
    try:
        engine = get_engine(database_url)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        return {
            "check_id": "database.connectivity",
            "status": "pass",
            "message": "Database connection succeeded.",
            "details": {"database_url": database_url},
        }
    except Exception as exc:
        return {
            "check_id": "database.connectivity",
            "status": "fail",
            "message": "Database connection failed.",
            "details": {"database_url": database_url, "error": str(exc)},
        }


def _check_migration_state(settings: Any) -> dict[str, object]:
    if settings.is_local_bind:
        return {
            "check_id": "database.migrations",
            "status": "skip",
            "message": "Local bind mode allows bootstrap metadata create_all.",
            "details": {"bind_address": settings.bind_address},
        }
    required_revision = os.getenv("SCHEMAPILOT_REQUIRED_DB_REVISION", "0001_initial_schema")
    try:
        ensure_required_revision(
            engine=get_engine(settings.database_url), required_revision=required_revision
        )
        return {
            "check_id": "database.migrations",
            "status": "pass",
            "message": "Database migration state matches required revision.",
            "details": {"required_revision": required_revision},
        }
    except StartupConfigurationError as exc:
        return {
            "check_id": "database.migrations",
            "status": "fail",
            "message": str(exc),
            "details": exc.details,
        }


def _check_no_bypass_ports() -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    errors = _collect_bypass_port_errors(root)
    if errors:
        return {
            "check_id": "deploy.no_bypass_ports",
            "status": "fail",
            "message": "Bypass ports are exposed in deploy artifacts.",
            "details": {"errors": errors},
        }
    return {
        "check_id": "deploy.no_bypass_ports",
        "status": "pass",
        "message": "No bypass ports exposed in deploy artifacts.",
        "details": {},
    }


def _check_auth_configuration(settings: Any) -> dict[str, object]:
    bind_address = str(settings.bind_address or "").strip()
    auth_mode = str(settings.auth_mode or "").strip().lower()
    is_non_local = not bool(getattr(settings, "is_local_bind", False))
    if is_non_local and not bool(settings.require_auth_for_non_local):
        return {
            "check_id": "auth.configuration",
            "status": "fail",
            "message": "Non-local bind requires auth guardrails.",
            "details": {
                "reason": "require_auth_for_non_local_disabled",
                "bind_address": bind_address,
                "auth_mode": auth_mode,
            },
        }
    if is_non_local and auth_mode == "local":
        return {
            "check_id": "auth.configuration",
            "status": "fail",
            "message": "Non-local bind must not use local token auth mode.",
            "details": {
                "reason": "non_local_local_auth_mode",
                "bind_address": bind_address,
                "auth_mode": auth_mode,
            },
        }
    return {
        "check_id": "auth.configuration",
        "status": "pass",
        "message": "Auth configuration is compatible with bind mode.",
        "details": {
            "bind_address": bind_address,
            "auth_mode": auth_mode,
            "require_auth_for_non_local": bool(settings.require_auth_for_non_local),
        },
    }


def _collect_bypass_port_errors(root: Path) -> list[str]:
    errors: list[str] = []
    compose_path = root / "deploy" / "docker-compose.yml"
    if compose_path.exists():
        compose = compose_path.read_text(encoding="utf-8")
        for token in BYPASS_TOKENS:
            if token in compose:
                errors.append(f"{compose_path.as_posix()}: contains mapping {token}")
        for mapping in COMPOSE_ONLY_BLOCKED_MAPPINGS:
            if mapping in compose:
                errors.append(f"{compose_path.as_posix()}: contains mapping {mapping}")
    for directory in [root / "deploy" / "k8s", root / "deploy" / "helm" / "templates"]:
        if not directory.exists():
            continue
        for file in sorted(directory.glob("*.yaml")):
            content = file.read_text(encoding="utf-8")
            for match in PORT_PATTERN.finditer(content):
                if int(match.group(1)) in BYPASS_PORTS:
                    errors.append(f"{file.as_posix()}: contains blocked port {match.group(1)}")
    return errors


def _check_secrets_backend_availability(settings: Any) -> dict[str, object]:
    try:
        backend = load_secrets_store(settings)
        if isinstance(backend, LocalEncryptedSecretsStore):
            root = Path(settings.secrets_store_root)
            root.mkdir(parents=True, exist_ok=True)
            return {
                "check_id": "secrets.backend",
                "status": "pass",
                "message": "Local encrypted secrets backend is available.",
                "details": {"backend": "local_encrypted", "root": root.as_posix()},
            }
        if isinstance(backend, VaultSecretsStore):
            if not settings.vault_url:
                raise StartupConfigurationError(
                    "Vault backend requires vault URL.",
                    details={"secrets_store_backend": "vault"},
                )
            health_url = settings.vault_url.rstrip("/") + "/v1/sys/health"
            with urllib.request.urlopen(health_url, timeout=3) as response:  # nosec B310
                status = int(getattr(response, "status", 200))
            if status >= 500:
                raise StartupConfigurationError(
                    "Vault health check returned server error.",
                    details={"status": status},
                )
            return {
                "check_id": "secrets.backend",
                "status": "pass",
                "message": "Vault secrets backend is reachable.",
                "details": {"backend": "vault", "vault_url": settings.vault_url},
            }
        return {
            "check_id": "secrets.backend",
            "status": "pass",
            "message": "Secrets backend loaded.",
            "details": {"backend": settings.secrets_store_backend},
        }
    except (StartupConfigurationError, OSError, TimeoutError, urllib.error.URLError) as exc:
        details = exc.details if isinstance(exc, StartupConfigurationError) else {"error": str(exc)}
        return {
            "check_id": "secrets.backend",
            "status": "fail",
            "message": "Secrets backend availability check failed.",
            "details": details,
        }


def _check_target_db_health(settings: Any) -> dict[str, object]:
    session_factory = get_session_factory(settings.database_url)
    try:
        with session_factory() as session:
            state_rows = session.execute(select(TargetDbState)).scalars().all()
            if not state_rows:
                return {
                    "check_id": "target_db.health",
                    "status": "skip",
                    "message": "No target DB state configured.",
                    "details": {},
                }
            active_target_ids = sorted(
                {
                    str(row.active_target_db_id).strip()
                    for row in state_rows
                    if str(row.active_target_db_id or "").strip()
                }
            )
            if not active_target_ids:
                return {
                    "check_id": "target_db.health",
                    "status": "skip",
                    "message": "No active target DB configured.",
                    "details": {},
                }
            errors: list[str] = []
            for target_db_id in active_target_ids:
                profile = session.get(TargetDbProfile, target_db_id)
                if profile is None:
                    errors.append(f"missing_target_db_profile:{target_db_id}")
                    continue
                if bool(profile.disabled):
                    errors.append(f"target_db_disabled:{target_db_id}")
                    continue
                has_connection = bool(profile.connection_json)
                has_credentials = bool(profile.credential_refs_json)
                if not has_connection and not has_credentials:
                    errors.append(f"target_db_connection_missing:{target_db_id}")
            if errors:
                return {
                    "check_id": "target_db.health",
                    "status": "fail",
                    "message": "Target DB health check failed.",
                    "details": {"errors": errors, "active_target_db_ids": active_target_ids},
                }
            return {
                "check_id": "target_db.health",
                "status": "pass",
                "message": "Active target DB profiles are healthy.",
                "details": {"active_target_db_ids": active_target_ids},
            }
    except Exception as exc:
        error_text = str(exc)
        if "no such table" in error_text.lower() or "does not exist" in error_text.lower():
            return {
                "check_id": "target_db.health",
                "status": "skip",
                "message": "Target DB metadata tables are not initialized yet.",
                "details": {"error": error_text},
            }
        return {
            "check_id": "target_db.health",
            "status": "fail",
            "message": "Target DB health check failed.",
            "details": {"error": error_text},
        }


def _check_plugin_sandbox_settings(settings: Any) -> dict[str, object]:
    errors: list[str] = []
    if bool(settings.plugin_network_enabled):
        errors.append("plugin_network_enabled")
    if int(settings.plugin_max_runtime_seconds) > 300:
        errors.append("plugin_max_runtime_seconds_exceeds_guardrail")
    if str(settings.profile).strip().lower() == "enterprise" and not str(
        settings.plugin_allowed_root or ""
    ).strip():
        errors.append("plugin_allowed_root_required_enterprise")
    if errors:
        return {
            "check_id": "plugin.sandbox",
            "status": "fail",
            "message": "Plugin sandbox settings are too permissive.",
            "details": {
                "errors": errors,
                "plugin_network_enabled": bool(settings.plugin_network_enabled),
                "plugin_max_runtime_seconds": int(settings.plugin_max_runtime_seconds),
                "plugin_allowed_root": str(settings.plugin_allowed_root or ""),
            },
        }
    return {
        "check_id": "plugin.sandbox",
        "status": "pass",
        "message": "Plugin sandbox settings are safe.",
        "details": {
            "plugin_network_enabled": bool(settings.plugin_network_enabled),
            "plugin_max_runtime_seconds": int(settings.plugin_max_runtime_seconds),
            "plugin_allowed_root": str(settings.plugin_allowed_root or ""),
        },
    }


def _check_jwks_reachability(settings: Any) -> dict[str, object]:
    if settings.auth_mode != "oidc_jwt" or not settings.oidc_jwks_url:
        return {
            "check_id": "oidc.jwks_reachability",
            "status": "skip",
            "message": "JWKS reachability check skipped (oidc_jwt not configured).",
            "details": {},
        }
    try:
        with urllib.request.urlopen(settings.oidc_jwks_url, timeout=3) as response:  # nosec B310
            payload = response.read().decode("utf-8", errors="ignore")
        if "keys" not in payload:
            raise ValueError("jwks_payload_missing_keys")
        return {
            "check_id": "oidc.jwks_reachability",
            "status": "pass",
            "message": "JWKS endpoint is reachable.",
            "details": {"oidc_jwks_url": settings.oidc_jwks_url},
        }
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        return {
            "check_id": "oidc.jwks_reachability",
            "status": "fail",
            "message": "JWKS endpoint reachability check failed.",
            "details": {"oidc_jwks_url": settings.oidc_jwks_url, "error": str(exc)},
        }


def list_remediation_ids() -> list[str]:
    """Return sorted remediation IDs used by doctor checks."""
    return sorted(set(CHECK_REMEDIATIONS.values()))


def remediation_for_check(check_id: str) -> str | None:
    """Resolve remediation ID for one check identifier."""
    return CHECK_REMEDIATIONS.get(str(check_id).strip())
