"""Optional local artifact encryption helpers with key rotation support."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactCryptoConfig:
    enabled: bool
    key_id: str
    key_material: str


def load_artifact_crypto_config() -> ArtifactCryptoConfig:
    enabled = os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    key_id = os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY_ID", "v1").strip() or "v1"
    key_material = os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY", "schemapilot-artifact-key")
    return ArtifactCryptoConfig(enabled=enabled, key_id=key_id, key_material=key_material)


def encrypt_payload(
    *, payload: dict[str, object], config: ArtifactCryptoConfig
) -> dict[str, object]:
    """Encrypt payload envelope when artifact encryption is enabled."""
    if not config.enabled:
        return {"encrypted": False, "payload": payload}
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    ciphertext = _encrypt(plaintext=plaintext, key_material=config.key_material)
    return {
        "encrypted": True,
        "key_id": config.key_id,
        "ciphertext": ciphertext,
    }


def decrypt_payload(
    *, envelope: dict[str, object], config: ArtifactCryptoConfig
) -> dict[str, object]:
    """Decrypt payload envelope if encrypted."""
    encrypted = bool(envelope.get("encrypted", False))
    if not encrypted:
        payload = envelope.get("payload", {})
        return payload if isinstance(payload, dict) else {}
    ciphertext = str(envelope.get("ciphertext", "")).strip()
    if not ciphertext:
        raise ValueError("artifact_payload_invalid")
    plaintext = _decrypt(ciphertext=ciphertext, key_material=config.key_material)
    parsed = json.loads(plaintext)
    if not isinstance(parsed, dict):
        raise ValueError("artifact_payload_invalid")
    return parsed


def _derive_key(material: str) -> bytes:
    return hashlib.sha256(material.encode("utf-8")).digest()


def _encrypt(*, plaintext: str, key_material: str) -> str:
    key = _derive_key(key_material)
    payload = plaintext.encode("utf-8")
    cipher = bytes(byte ^ key[idx % len(key)] for idx, byte in enumerate(payload))
    return base64.urlsafe_b64encode(cipher).decode("ascii")


def _decrypt(*, ciphertext: str, key_material: str) -> str:
    decoded = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    key = _derive_key(key_material)
    payload = bytes(byte ^ key[idx % len(key)] for idx, byte in enumerate(decoded))
    return payload.decode("utf-8")
