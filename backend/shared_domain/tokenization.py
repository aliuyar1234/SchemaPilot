"""Optional deterministic tokenization vault."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path

from backend.shared_domain.errors import DisabledIntegrationError, PolicyDeniedError


def _stable_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass
class TokenizationVault:
    """Simple local token vault with deterministic token IDs."""

    enabled: bool
    vault_path: Path
    signing_key: str
    key_id: str = "token-v1"

    def tokenize(
        self,
        *,
        workspace_id: str,
        value: str,
        namespace: str = "default",
        actor_id: str = "unknown",
    ) -> dict[str, object]:
        if not self.enabled:
            raise DisabledIntegrationError(
                "Tokenization vault is disabled.",
                details={"reason": "tokenization_disabled"},
            )
        normalized = value.strip()
        if not normalized:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "tokenization_value_required"},
            )
        token = self._token_for_value(
            workspace_id=workspace_id,
            namespace=namespace,
            value=normalized,
        )
        entry: dict[str, object] = {
            "workspace_id": workspace_id,
            "namespace": namespace,
            "token": token,
            "value": normalized,
            "actor_id": actor_id,
            "key_id": self.key_id,
        }
        self._append_entry(entry)
        return {"token": token, "namespace": namespace, "key_id": self.key_id}

    def detokenize(self, *, workspace_id: str, token: str, namespace: str = "default") -> str:
        if not self.enabled:
            raise DisabledIntegrationError(
                "Tokenization vault is disabled.",
                details={"reason": "tokenization_disabled"},
            )
        normalized_token = token.strip()
        if not normalized_token:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "token_required"},
            )
        for row in self._read_entries():
            if str(row.get("workspace_id", "")) != workspace_id:
                continue
            if str(row.get("namespace", "")) != namespace:
                continue
            if str(row.get("token", "")) != normalized_token:
                continue
            return str(row.get("value", ""))
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "token_not_found"},
        )

    def _token_for_value(self, *, workspace_id: str, namespace: str, value: str) -> str:
        canonical = _stable_json(
            {
                "workspace_id": workspace_id,
                "namespace": namespace,
                "value": value,
            }
        ).encode("utf-8")
        digest = hmac.new(self.signing_key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        return f"tok_{digest[:32]}"

    def _append_entry(self, entry: dict[str, object]) -> None:
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        with self.vault_path.open("a", encoding="utf-8") as handle:
            handle.write(_stable_json(entry) + "\n")

    def _read_entries(self) -> list[dict[str, object]]:
        if not self.vault_path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in self.vault_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append({str(key): value for key, value in payload.items()})
        return rows
