"""Optional audit sink plugins (disabled by default)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib import error as urlerror
from urllib import request as urlrequest

from backend.shared_domain.config import Settings
from backend.shared_domain.errors import StartupConfigurationError


class AuditSinkError(RuntimeError):
    """Raised when audit sink delivery fails."""


class AuditSink(Protocol):
    """Audit sink plugin contract."""

    def emit(self, event: dict[str, object]) -> None:
        """Emit an audit event to configured sink."""


class DisabledAuditSink:
    """No-op sink used when sink integration is disabled."""

    def emit(self, event: dict[str, object]) -> None:  # noqa: ARG002
        return None


@dataclass(frozen=True)
class JsonlAuditSink:
    """JSONL audit sink writing append-only local files."""

    target_path: Path

    def emit(self, event: dict[str, object]) -> None:
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        with self.target_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


@dataclass(frozen=True)
class WebhookAuditSink:
    """Webhook sink posting JSON payloads."""

    url: str

    def emit(self, event: dict[str, object]) -> None:
        body = json.dumps(event, sort_keys=True).encode("utf-8")
        req = urlrequest.Request(  # nosec B310 - URL from operator config
            self.url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlrequest.urlopen(req, timeout=3):  # nosec B310
                return None
        except (OSError, TimeoutError, urlerror.URLError) as exc:
            raise AuditSinkError("audit_sink_unavailable") from exc


def load_audit_sink(settings: Settings) -> AuditSink:
    """Load configured audit sink implementation."""
    sink_type = settings.audit_sink_type.strip().lower()
    if sink_type == "disabled":
        return DisabledAuditSink()
    if sink_type == "jsonl":
        if not settings.audit_sink_target:
            raise StartupConfigurationError(
                "JSONL audit sink requires target file path.",
                details={"audit_sink_type": sink_type},
            )
        return JsonlAuditSink(target_path=Path(settings.audit_sink_target))
    if sink_type == "webhook":
        if not settings.audit_sink_target:
            raise StartupConfigurationError(
                "Webhook audit sink requires target URL.",
                details={"audit_sink_type": sink_type},
            )
        return WebhookAuditSink(url=settings.audit_sink_target)
    raise StartupConfigurationError(
        "Unsupported audit sink type.",
        details={"audit_sink_type": sink_type},
    )
