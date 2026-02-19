"""Guided remediation actions for deterministic doctor findings."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from backend.shared_domain.config import Settings, load_settings
from cli.schemapilot_cli.doctor import list_remediation_ids, run_doctor_preflight


def run_guided_remediation(
    remediation_id: str, *, config_path: str | None = None
) -> dict[str, object]:
    """Run safe local remediation actions or return exact manual steps."""
    normalized = remediation_id.strip().upper()
    known = set(list_remediation_ids())
    if normalized not in known:
        raise ValueError(f"Unknown remediation ID: {normalized}")

    settings = _load_settings_safe(config_path=config_path)
    applied_actions: list[str] = []
    manual_steps = _manual_steps(normalized, settings=settings)

    if normalized == "DR-0002" and settings is not None:
        root = Path(settings.storage_root)
        root.mkdir(parents=True, exist_ok=True)
        applied_actions.append(f"created_directory:{root.as_posix()}")
    elif normalized == "DR-0003" and settings is not None:
        database_url = str(settings.database_url).strip()
        parsed = urlparse(database_url)
        if parsed.scheme.startswith("sqlite") and parsed.path:
            sqlite_path = Path(parsed.path.lstrip("/"))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            applied_actions.append(f"prepared_sqlite_parent:{sqlite_path.parent.as_posix()}")
    elif normalized == "DR-0007" and settings is not None:
        backend = str(settings.secrets_store_backend).strip().lower()
        if backend == "local_encrypted":
            root = Path(settings.secrets_store_root)
            root.mkdir(parents=True, exist_ok=True)
            applied_actions.append(f"created_directory:{root.as_posix()}")

    report = run_doctor_preflight(config_path=config_path)
    status = "manual_required"
    if applied_actions:
        status = "applied"
    if str(report.get("status", "fail")) == "ok":
        status = "resolved"
    return {
        "remediation_id": normalized,
        "status": status,
        "applied_actions": applied_actions,
        "manual_steps": manual_steps,
        "post_doctor_status": report.get("status", "fail"),
    }


def _load_settings_safe(*, config_path: str | None) -> Settings | None:
    try:
        return load_settings(config_path=config_path)
    except Exception:
        return None


def _manual_steps(remediation_id: str, *, settings: Settings | None) -> list[str]:
    if remediation_id == "DR-0001":
        return [
            "Open your config file and remove unknown keys.",
            (
                "Ensure required keys exist: profile, bind_address, auth_mode, "
                "database_url, storage_root."
            ),
            "Re-run `schemapilot doctor`.",
        ]
    if remediation_id == "DR-0004":
        return [
            "Run `schemapilot migrate-up` to apply metadata migrations.",
            "Set SCHEMAPILOT_REQUIRED_DB_REVISION to expected revision when running non-local.",
            "Re-run `schemapilot doctor`.",
        ]
    if remediation_id == "DR-0005":
        return [
            "Remove direct engine/index port mappings from deploy artifacts.",
            "Run `python tools/check_no_bypass_ports.py` to verify.",
            "Re-run `schemapilot doctor`.",
        ]
    if remediation_id == "DR-0006":
        return [
            "For non-local bind, set auth_mode to `oidc_jwt`.",
            "Keep require_auth_for_non_local=true.",
            "Re-run `schemapilot doctor`.",
        ]
    if remediation_id == "DR-0007":
        backend = str(settings.secrets_store_backend).strip().lower() if settings else "unknown"
        if backend == "vault":
            return [
                "Set SCHEMAPILOT_VAULT_URL and SCHEMAPILOT_VAULT_TOKEN.",
                "Verify Vault `/v1/sys/health` is reachable from this host.",
                "Re-run `schemapilot doctor`.",
            ]
        return [
            "Verify local encrypted secrets directory permissions.",
            "Re-run `schemapilot doctor`.",
        ]
    if remediation_id == "DR-0008":
        return [
            "Check active target DB profile exists and is not disabled.",
            "Ensure connection or credentials refs are configured for active target DB.",
            "Re-run `schemapilot doctor`.",
        ]
    if remediation_id == "DR-0009":
        return [
            "Set plugin_network_enabled=false.",
            "Set enterprise plugin_allowed_root when running enterprise profile.",
            "Keep plugin_max_runtime_seconds within safe bounds.",
            "Re-run `schemapilot doctor`.",
        ]
    if remediation_id == "DR-0010":
        return [
            "Set a reachable OIDC JWKS URL.",
            "Ensure JWKS payload contains `keys`.",
            "Re-run `schemapilot doctor`.",
        ]
    return [
        "Apply the related configuration fix and re-run `schemapilot doctor`.",
    ]
