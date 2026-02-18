#!/usr/bin/env python3
"""Generate and validate OpenAPI compatibility for control-plane and gateway APIs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings

OPENAPI_BASELINE_DIR = Path("openapi")
OPENAPI_BASELINES = {
    "control_plane": OPENAPI_BASELINE_DIR / "control_plane.v1.json",
    "gateway": OPENAPI_BASELINE_DIR / "gateway.v1.json",
}


def _default_settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/openapi_contract.db",
    )


def generate_current_openapi_specs() -> dict[str, dict[str, Any]]:
    """Generate current OpenAPI docs for both public services."""
    control_plane = create_app(settings_factory=_default_settings)
    gateway = create_gateway_app(settings_factory=_default_settings)
    return {
        "control_plane": control_plane.openapi(),
        "gateway": gateway.openapi(),
    }


def compare_openapi_compatibility(
    *,
    canonical: dict[str, Any],
    current: dict[str, Any],
    service_name: str,
) -> list[str]:
    """Check that current OpenAPI spec remains backward compatible with canonical."""
    errors: list[str] = []
    canonical_paths = canonical.get("paths", {})
    current_paths = current.get("paths", {})
    if not isinstance(canonical_paths, dict) or not isinstance(current_paths, dict):
        return [f"{service_name}: invalid OpenAPI paths structure"]
    for path, canonical_methods_raw in canonical_paths.items():
        if path not in current_paths:
            errors.append(f"{service_name}: missing path {path}")
            continue
        canonical_methods = (
            canonical_methods_raw if isinstance(canonical_methods_raw, dict) else {}
        )
        current_methods_raw = current_paths.get(path, {})
        current_methods = current_methods_raw if isinstance(current_methods_raw, dict) else {}
        for method, canonical_operation_raw in canonical_methods.items():
            if method not in current_methods:
                errors.append(f"{service_name}: missing method {method.upper()} {path}")
                continue
            canonical_operation = (
                canonical_operation_raw if isinstance(canonical_operation_raw, dict) else {}
            )
            current_operation_raw = current_methods.get(method, {})
            current_operation = (
                current_operation_raw if isinstance(current_operation_raw, dict) else {}
            )
            errors.extend(
                _compare_operation_responses(
                    canonical=canonical_operation,
                    current=current_operation,
                    service_name=service_name,
                    path=path,
                    method=method,
                )
            )
    return errors


def _compare_operation_responses(
    *,
    canonical: dict[str, Any],
    current: dict[str, Any],
    service_name: str,
    path: str,
    method: str,
) -> list[str]:
    errors: list[str] = []
    canonical_responses_raw = canonical.get("responses", {})
    current_responses_raw = current.get("responses", {})
    canonical_responses = (
        canonical_responses_raw if isinstance(canonical_responses_raw, dict) else {}
    )
    current_responses = current_responses_raw if isinstance(current_responses_raw, dict) else {}
    for status_code in canonical_responses:
        if status_code not in current_responses:
            errors.append(
                f"{service_name}: missing response {status_code} for {method.upper()} {path}"
            )
    return errors


def validate_openapi_compatibility(root: Path) -> list[str]:
    """Validate canonical OpenAPI baselines against current generated docs."""
    specs = generate_current_openapi_specs()
    errors: list[str] = []
    for service_name, baseline_path in OPENAPI_BASELINES.items():
        path = root / baseline_path
        if not path.exists():
            errors.append(f"{service_name}: missing baseline file {path.as_posix()}")
            continue
        canonical = json.loads(path.read_text(encoding="utf-8"))
        current = specs[service_name]
        errors.extend(
            compare_openapi_compatibility(
                canonical=canonical,
                current=current,
                service_name=service_name,
            )
        )
    return errors


def update_openapi_baselines(root: Path) -> None:
    """Write current OpenAPI specs as canonical baselines."""
    specs = generate_current_openapi_specs()
    for service_name, baseline_path in OPENAPI_BASELINES.items():
        path = root / baseline_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(specs[service_name], indent=2, sort_keys=True), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="Regenerate baseline files.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.update:
        update_openapi_baselines(root)
        print("PASS OpenAPI baselines updated")
        return 0
    errors = validate_openapi_compatibility(root)
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("PASS CHK-CONTRACT-COMPAT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
