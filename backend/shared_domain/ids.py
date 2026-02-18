"""Identifier helpers for UUID and ULID generation."""

from __future__ import annotations

import datetime as dt
import string
import threading
import uuid

ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_LOCK = threading.Lock()
_LAST_ULID_MILLIS = 0
_LAST_ULID_COUNTER = -1


def new_uuid() -> str:
    """Generate UUID string."""
    return str(uuid.uuid4())


def new_ulid() -> str:
    """Generate a simple ULID-compatible identifier.

    This implementation is deterministic in format and monotonic per-process.
    """
    global _LAST_ULID_MILLIS, _LAST_ULID_COUNTER
    with _ULID_LOCK:
        millis = int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)
        if millis == _LAST_ULID_MILLIS:
            _LAST_ULID_COUNTER += 1
        else:
            _LAST_ULID_MILLIS = millis
            _LAST_ULID_COUNTER = 0
        ts = _encode_base32(millis, length=10)
        counter = _encode_base32(_LAST_ULID_COUNTER, length=16)
    return ts + counter


def _encode_base32(value: int, *, length: int) -> str:
    chars: list[str] = []
    current = value
    while current > 0:
        current, remainder = divmod(current, 32)
        chars.append(ULID_ALPHABET[remainder])
    encoded = "".join(reversed(chars)) or "0"
    return encoded.rjust(length, "0")[:length]


def is_uuid(value: str) -> bool:
    """Validate UUID string."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def is_ulid(value: str) -> bool:
    """Validate ULID format (length + character set only)."""
    if len(value) != 26:
        return False
    return all(char in string.ascii_uppercase + string.digits for char in value)
