"""Deterministic SQL lineage extraction for simple SELECT transforms."""

from __future__ import annotations

import re

_SELECT_RE = re.compile(r"select\s+(?P<select>.+?)\s+from\s+", flags=re.IGNORECASE | re.DOTALL)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def derive_column_lineage(sql_text: str) -> list[dict[str, object]]:
    """Extract output column lineage from simple select expressions."""
    match = _SELECT_RE.search(sql_text.strip())
    if match is None:
        return []
    select_clause = match.group("select")
    parts = [part.strip() for part in select_clause.split(",") if part.strip()]
    lineage: list[dict[str, object]] = []
    for index, part in enumerate(parts):
        lowered = part.lower()
        if " as " in lowered:
            expression, alias = re.split(r"\s+as\s+", part, flags=re.IGNORECASE, maxsplit=1)
            output_column = alias.strip()
        else:
            expression = part
            output_column = f"col_{index + 1}"
        source_columns = [
            token
            for token in sorted({token.lower() for token in _IDENT_RE.findall(expression)})
            if token not in {"sum", "avg", "count", "min", "max"}
        ]
        lineage.append(
            {
                "output_column": output_column,
                "expression": expression.strip(),
                "source_columns": source_columns,
            }
        )
    return lineage
