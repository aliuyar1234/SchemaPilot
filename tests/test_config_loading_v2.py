from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.shared_domain.config import load_settings
from backend.shared_domain.errors import StartupConfigurationError


def test_load_settings_applies_json_config_overrides(tmp_path: Path) -> None:
    config = {
        "profile": "team",
        "bind_address": "127.0.0.1",
        "auth_mode": "local",
        "database_url": f"sqlite:///{(tmp_path / 'config.db').as_posix()}",
        "storage_root": (tmp_path / "storage").as_posix(),
        "worker_max_active_per_workspace": 3,
    }
    config_path = tmp_path / "schemapilot.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    settings = load_settings(config_path=config_path.as_posix())
    assert settings.profile == "team"
    assert settings.worker_max_active_per_workspace == 3
    assert settings.storage_root == (tmp_path / "storage").as_posix()


def test_load_settings_rejects_unknown_config_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text(json.dumps({"unknown_field": "x"}), encoding="utf-8")
    try:
        load_settings(config_path=config_path.as_posix())
    except StartupConfigurationError as exc:
        assert "Unknown settings keys are not allowed." in str(exc)
        assert exc.details.get("unknown_keys") == ["unknown_field"]
    else:  # pragma: no cover
        raise AssertionError("Expected StartupConfigurationError for unknown config keys")


def test_load_settings_supports_simple_yaml_config(tmp_path: Path) -> None:
    config_path = tmp_path / "schemapilot.yaml"
    config_path.write_text(
        "\n".join(
            [
                "profile: enterprise",
                "bind_address: 127.0.0.1",
                "auth_mode: oidc_jwt",
                "oidc_jwks_url: http://localhost/jwks",
                "require_auth_for_non_local: true",
                "oidc_jwt_allowed_algs: [HS256,RS256]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    settings = load_settings(config_path=config_path.as_posix())
    assert settings.profile == "enterprise"
    assert settings.auth_mode == "oidc_jwt"
    assert settings.oidc_jwks_url == "http://localhost/jwks"
    assert settings.oidc_jwt_allowed_algs == ("HS256", "RS256")


def test_settings_redaction_hides_sensitive_values(tmp_path: Path) -> None:
    config_path = tmp_path / "secret.json"
    config_path.write_text(
        json.dumps(
            {
                "database_url": "postgresql://user:pw@localhost:5432/schemapilot",
                "secrets_master_key": "super-secret",
                "vault_token": "vault-token",
                "audit_sink_target": "https://sink.example?token=abc",
                "plugin_signing_key": "plugin-secret-key",
            }
        ),
        encoding="utf-8",
    )
    settings = load_settings(config_path=config_path.as_posix())
    redacted = settings.to_redacted_dict()
    assert redacted["database_url"] == "postgresql://<redacted>@localhost:5432/schemapilot"
    assert redacted["secrets_master_key"] == "<redacted>"
    assert redacted["vault_token"] == "<redacted>"
    assert redacted["audit_sink_target"] == "<redacted>"
    assert redacted["plugin_signing_key"] == "<redacted>"


def test_load_settings_rejects_direct_ai_engine_env_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHEMAPILOT_AI_TRINO_URL", "http://trino:8080")
    with pytest.raises(StartupConfigurationError) as exc_info:
        load_settings()
    assert exc_info.value.details.get("reason") == "ai_direct_engine_config_present"
    assert "SCHEMAPILOT_AI_TRINO_URL" in list(exc_info.value.details.get("keys", []))
