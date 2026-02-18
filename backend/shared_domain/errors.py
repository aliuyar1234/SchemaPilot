"""Shared error types and stable API error codes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorPayload:
    """Structured error payload shape used by API responses."""

    code: str
    message: str
    details: dict[str, Any]


class SchemaPilotError(Exception):
    """Base typed error."""

    error_code = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class StartupConfigurationError(SchemaPilotError):
    """Raised when startup configuration violates security baseline."""

    error_code = "STARTUP_CONFIGURATION_ERROR"


class PolicyDeniedError(SchemaPilotError):
    """Raised when policy evaluation denies a request."""

    error_code = "POLICY_DENIED"


class NotFoundError(SchemaPilotError):
    """Raised when a requested resource does not exist."""

    error_code = "NOT_FOUND"


class DisabledIntegrationError(SchemaPilotError):
    """Raised when an optional integration is disabled."""

    error_code = "INTEGRATION_DISABLED"
