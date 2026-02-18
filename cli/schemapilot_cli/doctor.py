"""CLI doctor preflight checks for operator readiness."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.shared_domain.config import load_settings
from backend.shared_domain.db import ensure_required_revision, get_engine
from backend.shared_domain.errors import StartupConfigurationError
from backend.shared_domain.secrets_store import (
    LocalEncryptedSecretsStore,
    VaultSecretsStore,
    load_secrets_store,
)

BYPASS_PORTS = (8080, 8083, 9200, 6333)
BYPASS_TOKENS = tuple(f"{port}:{port}" for port in BYPASS_PORTS)
PORT_PATTERN = re.compile(r"\b(?:port|targetPort|nodePort)\s*:\s*(\d+)\b")


def run_doctor_preflight(*, config_path: str | None = None) -> dict[str, object]:
    """Run deterministic doctor checks and return structured report."""
    checks: list[dict[str, object]] = []
    settings = None
    settings_error = None
    try:
        settings = load_settings(config_path=config_path)
        checks.append(
            {
                "check_id": "settings.load",
                "status": "pass",
                "message": "Settings loaded and validated.",
                "details": settings.to_redacted_dict(),
            }
        )
    except StartupConfigurationError as exc:
        settings_error = exc
        checks.append(
            {
                "check_id": "settings.load",
                "status": "fail",
                "message": str(exc),
                "details": exc.details,
            }
        )
    if settings is None:
        return {
            "status": "fail",
            "checks": checks,
            "config_path": config_path or os.getenv("SCHEMAPILOT_CONFIG_FILE"),
            "error": str(settings_error) if settings_error is not None else "settings_not_loaded",
        }

    checks.append(_check_storage_writable(settings.storage_root))
    checks.append(_check_database_connectivity(settings.database_url))
    checks.append(_check_migration_state(settings))
    checks.append(_check_no_bypass_ports())
    checks.append(_check_secrets_backend_availability(settings))
    checks.append(_check_jwks_reachability(settings))
    failed = [item for item in checks if item.get("status") == "fail"]
    return {
        "status": "fail" if failed else "ok",
        "checks": checks,
        "config_path": config_path or os.getenv("SCHEMAPILOT_CONFIG_FILE"),
    }


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


def _collect_bypass_port_errors(root: Path) -> list[str]:
    errors: list[str] = []
    compose_path = root / "deploy" / "docker-compose.yml"
    if compose_path.exists():
        compose = compose_path.read_text(encoding="utf-8")
        for token in BYPASS_TOKENS:
            if token in compose:
                errors.append(f"{compose_path.as_posix()}: contains mapping {token}")
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
