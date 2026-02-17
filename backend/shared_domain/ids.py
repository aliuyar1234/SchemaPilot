"""Identifier helpers for UUID and ULID generation."""

from __future__ import annotations

import datetime as dt
import random
import string
import uuid

ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_uuid() -> str:
    """Generate UUID string."""
    return str(uuid.uuid4())


def new_ulid() -> str:
    """Generate a simple ULID-compatible identifier.

    This bootstrap implementation is deterministic in format and sortable by time prefix.
    """
    millis = int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)
    ts = _encode_base32(millis, length=10)
    rand = "".join(random.choice(ULID_ALPHABET) for _ in range(16))
    return ts + rand


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
