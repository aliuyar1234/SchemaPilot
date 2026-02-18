"""Deterministic anomaly detection on profiling summaries."""

from __future__ import annotations

from typing import Any


def detect_profile_anomalies(profile: dict[str, Any]) -> list[dict[str, object]]:
    """Detect simple data quality anomalies from profile summary."""
    anomalies: list[dict[str, object]] = []
    parse_error_rate = _as_float(profile.get("parse_error_rate"), default=0.0)
    if parse_error_rate > 0.05:
        anomalies.append(
            {
                "type": "parse_error_spike",
                "severity": "high",
                "message": f"parse_error_rate {parse_error_rate:.4f} exceeds 0.05 threshold",
            }
        )
    null_rates = profile.get("null_rates", {})
    if isinstance(null_rates, dict):
        for column in sorted(null_rates):
            rate = _as_float(null_rates.get(column), default=0.0)
            if rate > 0.7:
                anomalies.append(
                    {
                        "type": "high_null_rate",
                        "severity": "medium",
                        "column": str(column),
                        "message": f"null_rate {rate:.4f} exceeds 0.70 threshold",
                    }
                )
    unique_ratio = profile.get("unique_ratio", {})
    if isinstance(unique_ratio, dict):
        for column in sorted(unique_ratio):
            ratio = _as_float(unique_ratio.get(column), default=0.0)
            if 0.0 < ratio < 0.01:
                anomalies.append(
                    {
                        "type": "low_uniqueness",
                        "severity": "medium",
                        "column": str(column),
                        "message": f"unique_ratio {ratio:.4f} is below 0.01 threshold",
                    }
                )
    return anomalies


def _as_float(value: object, *, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default
