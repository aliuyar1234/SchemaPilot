"""Optional alert sink integrations for SLA/drift notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from backend.shared_domain.config import Settings


class AlertSinkError(RuntimeError):
    """Raised when alert delivery fails."""


class AlertSink:
    """Alert sink contract."""

    def emit(self, alert: dict[str, object]) -> None:
        raise NotImplementedError


class DisabledAlertSink(AlertSink):
    """No-op alert sink."""

    def emit(self, alert: dict[str, object]) -> None:
        _ = alert


@dataclass(frozen=True)
class JsonlAlertSink(AlertSink):
    """Append alerts as JSONL for local operator consumption."""

    output_path: Path

    def emit(self, alert: dict[str, object]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(alert, sort_keys=True) + "\n")


@dataclass(frozen=True)
class WebhookAlertSink(AlertSink):
    """POST alerts to a remote webhook."""

    target_url: str
    timeout_seconds: float

    def emit(self, alert: dict[str, object]) -> None:
        _validate_webhook_url(self.target_url)
        payload = json.dumps(alert, separators=(",", ":"), sort_keys=True).encode("utf-8")
        req = urlrequest.Request(
            self.target_url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout_seconds) as response:  # nosec B310
                if int(getattr(response, "status", 200)) >= 400:
                    raise AlertSinkError(f"webhook_http_{response.status}")
        except (urlerror.URLError, TimeoutError) as exc:
            raise AlertSinkError(f"webhook_delivery_failed:{exc}") from exc


def _validate_webhook_url(target_url: str) -> None:
    parsed = urlparse.urlparse(target_url)
    if parsed.scheme not in {"http", "https"}:
        raise AlertSinkError("webhook_scheme_not_allowed")
    if not parsed.netloc:
        raise AlertSinkError("webhook_host_required")


def load_alert_sink(settings: Settings) -> AlertSink:
    """Load alert sink using optional settings or env defaults."""
    sink_type = str(getattr(settings, "alert_sink_type", "disabled")).strip().lower()
    sink_target = str(getattr(settings, "alert_sink_target", "") or "").strip()
    timeout_ms_raw = getattr(settings, "alert_sink_timeout_ms", 3000)
    timeout_ms = int(timeout_ms_raw) if isinstance(timeout_ms_raw, (int, float, str)) else 3000
    timeout_seconds = max(timeout_ms, 1) / 1000.0
    if sink_type in {"", "disabled", "none"}:
        return DisabledAlertSink()
    if sink_type == "jsonl":
        target = Path(sink_target or "./runtime/alerts/alerts.jsonl")
        return JsonlAlertSink(output_path=target)
    if sink_type == "webhook":
        if not sink_target:
            raise ValueError("alert_sink_target_required")
        return WebhookAlertSink(target_url=sink_target, timeout_seconds=timeout_seconds)
    raise ValueError(f"unsupported_alert_sink_type:{sink_type}")
