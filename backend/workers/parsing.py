"""Locale and encoding-aware parsing helpers."""

from __future__ import annotations

import csv
import datetime as dt
import re
import unicodedata
from pathlib import Path
from typing import TextIO

_CURRENCY_CLEAN_RE = re.compile(r"[^0-9,.\-]")
_DATE_SPLIT_RE = re.compile(r"[-/]")


def normalize_text(value: str) -> str:
    """Normalize unicode text into deterministic NFKC representation."""
    return unicodedata.normalize("NFKC", value).strip()


def parse_currency(value: str) -> float:
    """Parse localized currency number string to float."""
    normalized = normalize_text(value)
    cleaned = _CURRENCY_CLEAN_RE.sub("", normalized)
    if not cleaned:
        raise ValueError("currency_empty")
    comma_count = cleaned.count(",")
    dot_count = cleaned.count(".")
    if comma_count and dot_count:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif comma_count and not dot_count:
        cleaned = cleaned.replace(",", ".")
    return float(cleaned)


def parse_date(value: str, *, day_first: bool | None = None) -> dt.date:
    """Parse date with ambiguity detection for locale-sensitive formats."""
    normalized = normalize_text(value)
    try:
        return dt.date.fromisoformat(normalized)
    except ValueError:
        pass
    parts = [part for part in _DATE_SPLIT_RE.split(normalized) if part]
    if len(parts) != 3:
        raise ValueError("date_unparseable")
    if not all(part.isdigit() for part in parts):
        raise ValueError("date_unparseable")
    a, b, c = (int(part) for part in parts)
    if c < 100:
        raise ValueError("date_unparseable")
    if day_first is None and a <= 12 and b <= 12:
        raise ValueError("date_ambiguous")
    day, month = (a, b) if day_first else (b, a)
    return dt.date(c, month, day)


def open_csv_reader_with_fallback(path: str) -> tuple[TextIO, csv.DictReader[str]]:
    """Open CSV reader with encoding fallbacks for common export files."""
    file_path = Path(path)
    encodings = ("utf-8", "utf-8-sig", "latin-1")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            handle = file_path.open("r", encoding=encoding, newline="")
            reader: csv.DictReader[str] = csv.DictReader(handle)
            # Touch header to force decode on open/read path.
            _ = reader.fieldnames
            return handle, reader
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"encoding_unreadable:{file_path.as_posix()}") from last_error
