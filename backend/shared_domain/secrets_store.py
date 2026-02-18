"""Secrets store abstraction with local-encrypted and vault adapters."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib import error as urlerror
from urllib import request as urlrequest

from backend.shared_domain.config import Settings
from backend.shared_domain.errors import DisabledIntegrationError, StartupConfigurationError
from backend.shared_domain.ids import new_ulid


class SecretsStoreError(RuntimeError):
    """Raised when secret storage or retrieval fails."""


class SecretsStore(Protocol):
    """Secrets storage contract."""

    def put_secret(self, *, scope: str, key: str, value: str) -> str:
        """Store secret value and return opaque reference."""

    def get_secret(self, reference: str) -> str:
        """Resolve secret by opaque reference."""


@dataclass(frozen=True)
class LocalEncryptedSecretsStore:
    """Local encrypted secrets store for default deployments."""

    root: Path
    master_key: str

    def put_secret(self, *, scope: str, key: str, value: str) -> str:
        if not value:
            raise SecretsStoreError("secret_value_required")
        ref_id = new_ulid()
        reference = f"secret://local/{scope}/{key}/{ref_id}"
        payload = {
            "scope": scope,
            "key": key,
            "ciphertext": _encrypt(value=value, master_key=self.master_key),
        }
        path = self._path_for_reference(reference)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return reference

    def get_secret(self, reference: str) -> str:
        path = self._path_for_reference(reference)
        if not path.exists():
            raise SecretsStoreError("secret_not_found")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SecretsStoreError("secret_payload_invalid") from exc
        ciphertext = str(payload.get("ciphertext", ""))
        if not ciphertext:
            raise SecretsStoreError("secret_payload_invalid")
        return _decrypt(ciphertext=ciphertext, master_key=self.master_key)

    def _path_for_reference(self, reference: str) -> Path:
        if not reference.startswith("secret://local/"):
            raise SecretsStoreError("secret_reference_invalid")
        suffix = reference.removeprefix("secret://local/")
        return self.root / (suffix.replace("/", "__") + ".json")


@dataclass(frozen=True)
class VaultSecretsStore:
    """Vault-backed secrets store adapter (opt-in)."""

    url: str
    token: str

    def put_secret(self, *, scope: str, key: str, value: str) -> str:
        path = f"schemapilot/{scope}/{key}/{new_ulid()}"
        payload = {"data": {"value": value}}
        self._request_json(
            method="POST",
            path=f"/v1/secret/data/{path}",
            payload=payload,
        )
        return f"secret://vault/{path}"

    def get_secret(self, reference: str) -> str:
        if not reference.startswith("secret://vault/"):
            raise SecretsStoreError("secret_reference_invalid")
        path = reference.removeprefix("secret://vault/")
        payload = self._request_json(method="GET", path=f"/v1/secret/data/{path}")
        data = payload.get("data", {})
        if not isinstance(data, dict):
            raise SecretsStoreError("secret_payload_invalid")
        nested = data.get("data", {})
        if not isinstance(nested, dict):
            raise SecretsStoreError("secret_payload_invalid")
        value = str(nested.get("value", ""))
        if not value:
            raise SecretsStoreError("secret_not_found")
        return value

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        body = json.dumps(payload, sort_keys=True).encode("utf-8") if payload else None
        req = urlrequest.Request(  # nosec B310 - URL from operator config
            self.url.rstrip("/") + path,
            data=body,
            method=method,
            headers={
                "X-Vault-Token": self.token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=3) as response:  # nosec B310
                raw = response.read().decode("utf-8")
        except (OSError, TimeoutError, urlerror.URLError) as exc:
            raise SecretsStoreError("vault_unavailable") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SecretsStoreError("vault_invalid_response") from exc
        if not isinstance(parsed, dict):
            raise SecretsStoreError("vault_invalid_response")
        return {str(k): v for k, v in parsed.items()}


def load_secrets_store(settings: Settings) -> SecretsStore:
    """Load configured secrets store implementation."""
    backend = settings.secrets_store_backend.strip().lower()
    if backend == "local_encrypted":
        master_key = settings.secrets_master_key or "schemapilot-local-dev-master-key"
        return LocalEncryptedSecretsStore(
            root=Path(settings.secrets_store_root),
            master_key=master_key,
        )
    if backend == "vault":
        if not settings.vault_url or not settings.vault_token:
            raise StartupConfigurationError(
                "Vault secrets backend requires URL and token configuration.",
                details={"secrets_store_backend": backend},
            )
        return VaultSecretsStore(url=settings.vault_url, token=settings.vault_token)
    raise DisabledIntegrationError(
        "Secrets store backend is disabled.",
        details={"secrets_store_backend": backend},
    )


def _derive_key(master_key: str) -> bytes:
    return hashlib.sha256(master_key.encode("utf-8")).digest()


def _encrypt(*, value: str, master_key: str) -> str:
    key = _derive_key(master_key)
    data = value.encode("utf-8")
    cipher = bytes(byte ^ key[idx % len(key)] for idx, byte in enumerate(data))
    return base64.urlsafe_b64encode(cipher).decode("ascii")


def _decrypt(*, ciphertext: str, master_key: str) -> str:
    try:
        payload = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    except ValueError as exc:
        raise SecretsStoreError("secret_payload_invalid") from exc
    key = _derive_key(master_key)
    plain = bytes(byte ^ key[idx % len(key)] for idx, byte in enumerate(payload))
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretsStoreError("secret_payload_invalid") from exc

