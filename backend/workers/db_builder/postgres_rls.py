"""Optional deterministic Postgres RLS policy planning."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class PostgresRlsPlan:
    """RLS planning payload."""

    plan_checksum: str
    statements: list[str]
    policy_rows: list[dict[str, object]]


def build_postgres_rls_plan(
    *,
    workspace_id: str,
    target_db_id: str,
    schema: str,
    semantic_manifest: dict[str, object],
) -> PostgresRlsPlan:
    """Create a conservative workspace-id RLS plan for postgres targets."""
    entities_raw = semantic_manifest.get("entities", [])
    entities = entities_raw if isinstance(entities_raw, list) else []
    policy_rows: list[dict[str, object]] = []
    statements: list[str] = []
    for entity_raw in entities:
        if not isinstance(entity_raw, dict):
            continue
        table = _safe_identifier(entity_raw.get("entity_id"))
        if table is None:
            continue
        policy_name = f"sp_ws_iso_{table}"
        using_clause = "workspace_id = current_setting('schemapilot.workspace_id', true)"
        policy_rows.append(
            {
                "table": table,
                "policy_name": policy_name,
                "using": using_clause,
                "check": using_clause,
            }
        )
        statements.extend(
            [
                f'ALTER TABLE "{schema}"."{table}" ENABLE ROW LEVEL SECURITY;',
                f'CREATE POLICY "{policy_name}" ON "{schema}"."{table}" '
                f'USING ({using_clause}) WITH CHECK ({using_clause});',
            ]
        )
    checksum = _stable_checksum(
        {
            "workspace_id": workspace_id,
            "target_db_id": target_db_id,
            "schema": schema,
            "policy_rows": policy_rows,
            "statements": statements,
        }
    )
    return PostgresRlsPlan(
        plan_checksum=checksum,
        statements=statements,
        policy_rows=policy_rows,
    )


def _safe_identifier(value: object) -> str | None:
    candidate = str(value).strip()
    if not candidate:
        return None
    if not _SAFE_IDENTIFIER.fullmatch(candidate):
        return None
    return candidate.lower()


def _stable_checksum(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
