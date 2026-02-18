"""Deterministic gold template pack registry and generator."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from backend.shared_domain.semantic import semantic_manifest_checksum, validate_semantic_manifest

GOLD_TEMPLATE_PACKS: dict[str, dict[str, object]] = {
    "invoices": {
        "pack_id": "invoices",
        "description": "Starter invoice analytics pack",
        "required_columns": ["invoice_id", "customer_id", "amount", "invoice_date"],
        "gold_models": [
            {
                "model_name": "invoice_daily_revenue",
                "sql": (
                    "select invoice_date, sum(amount) as gross_revenue "
                    "from silver.invoice group by invoice_date"
                ),
            }
        ],
        "semantic_manifest": {
            "manifest_version": "1",
            "workspace_id": "{workspace_id}",
            "entities": [
                {
                    "entity_id": "invoice",
                    "dataset_id": "dataset-invoice",
                    "primary_key": "invoice_id",
                    "attributes": ["customer_id", "amount", "invoice_date"],
                },
                {
                    "entity_id": "customer",
                    "dataset_id": "dataset-customer",
                    "primary_key": "customer_id",
                    "attributes": ["customer_name", "region"],
                },
            ],
            "metrics": [
                {
                    "metric_id": "gross_revenue",
                    "entity_id": "invoice",
                    "aggregation": "sum",
                    "field": "amount",
                    "expression": "sum(amount)",
                },
                {
                    "metric_id": "invoice_count",
                    "entity_id": "invoice",
                    "aggregation": "count",
                    "field": "invoice_id",
                    "expression": "count(invoice_id)",
                },
            ],
            "joins": [
                {
                    "join_id": "invoice_customer",
                    "left_entity_id": "invoice",
                    "right_entity_id": "customer",
                    "left_key": "customer_id",
                    "right_key": "customer_id",
                    "join_type": "left",
                }
            ],
        },
    },
    "crm": {
        "pack_id": "crm",
        "description": "Starter CRM pipeline and conversion pack",
        "required_columns": ["lead_id", "stage", "owner_id", "created_at"],
        "gold_models": [
            {
                "model_name": "crm_pipeline_stage_counts",
                "sql": (
                    "select stage, count(lead_id) as lead_count from silver.lead group by stage"
                ),
            }
        ],
        "semantic_manifest": {
            "manifest_version": "1",
            "workspace_id": "{workspace_id}",
            "entities": [
                {
                    "entity_id": "lead",
                    "dataset_id": "dataset-lead",
                    "primary_key": "lead_id",
                    "attributes": ["stage", "owner_id", "created_at"],
                },
                {
                    "entity_id": "owner",
                    "dataset_id": "dataset-owner",
                    "primary_key": "owner_id",
                    "attributes": ["owner_name", "team"],
                },
            ],
            "metrics": [
                {
                    "metric_id": "lead_count",
                    "entity_id": "lead",
                    "aggregation": "count",
                    "field": "lead_id",
                    "expression": "count(lead_id)",
                }
            ],
            "joins": [
                {
                    "join_id": "lead_owner",
                    "left_entity_id": "lead",
                    "right_entity_id": "owner",
                    "left_key": "owner_id",
                    "right_key": "owner_id",
                    "join_type": "left",
                }
            ],
        },
    },
    "support": {
        "pack_id": "support",
        "description": "Starter support ticket SLA pack",
        "required_columns": ["ticket_id", "status", "priority", "opened_at", "closed_at"],
        "gold_models": [
            {
                "model_name": "support_ticket_backlog",
                "sql": (
                    "select status, priority, count(ticket_id) as ticket_count "
                    "from silver.ticket group by status, priority"
                ),
            }
        ],
        "semantic_manifest": {
            "manifest_version": "1",
            "workspace_id": "{workspace_id}",
            "entities": [
                {
                    "entity_id": "ticket",
                    "dataset_id": "dataset-ticket",
                    "primary_key": "ticket_id",
                    "attributes": ["status", "priority", "opened_at", "closed_at"],
                }
            ],
            "metrics": [
                {
                    "metric_id": "ticket_count",
                    "entity_id": "ticket",
                    "aggregation": "count",
                    "field": "ticket_id",
                    "expression": "count(ticket_id)",
                }
            ],
            "joins": [],
        },
    },
}


def list_gold_template_packs() -> list[str]:
    """List available gold template pack IDs."""
    return sorted(GOLD_TEMPLATE_PACKS)


def load_gold_template_pack(pack_id: str) -> dict[str, object]:
    """Load one template pack by ID."""
    key = pack_id.strip().lower()
    pack = GOLD_TEMPLATE_PACKS.get(key)
    if pack is None:
        raise ValueError(f"unknown_template_pack:{key}")
    return copy.deepcopy(pack)


def generate_gold_template_bundle(
    *,
    pack_id: str,
    workspace_id: str,
    output_root: str,
    overwrite: bool = False,
) -> dict[str, object]:
    """Generate deterministic bundle payload and write it to disk."""
    if not workspace_id.strip():
        raise ValueError("workspace_id_required")
    pack = load_gold_template_pack(pack_id)
    manifest_raw = pack.get("semantic_manifest", {})
    if not isinstance(manifest_raw, dict):
        raise ValueError("template_manifest_invalid")
    manifest = copy.deepcopy(manifest_raw)
    manifest["workspace_id"] = workspace_id
    validated_manifest = validate_semantic_manifest(
        manifest,
        expected_workspace_id=workspace_id,
    )
    checksum = semantic_manifest_checksum(validated_manifest)
    required_columns_raw = pack.get("required_columns", [])
    required_columns = (
        sorted(
            {
                str(value)
                for value in required_columns_raw
                if isinstance(value, str) and value.strip()
            }
        )
        if isinstance(required_columns_raw, list)
        else []
    )
    gold_models_raw = pack.get("gold_models", [])
    gold_models = (
        [
            {
                "model_name": str(model.get("model_name", "")),
                "sql": str(model.get("sql", "")),
            }
            for model in gold_models_raw
            if isinstance(model, dict)
        ]
        if isinstance(gold_models_raw, list)
        else []
    )
    entities = _as_list(validated_manifest.get("entities", []))
    metrics = _as_list(validated_manifest.get("metrics", []))
    joins = _as_list(validated_manifest.get("joins", []))

    bundle = {
        "pack_id": str(pack["pack_id"]),
        "workspace_id": workspace_id,
        "description": str(pack.get("description", "")),
        "required_columns": required_columns,
        "gold_models": gold_models,
        "semantic_manifest": validated_manifest,
        "semantic_manifest_checksum": checksum,
    }

    output_dir = Path(output_root) / workspace_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{pack_id.strip().lower()}.json"
    if output_path.exists() and not overwrite:
        raise ValueError("template_bundle_exists")
    serialized = json.dumps(bundle, indent=2, sort_keys=True)
    output_path.write_text(serialized + "\n", encoding="utf-8")
    return {
        "pack_id": str(pack["pack_id"]),
        "workspace_id": workspace_id,
        "output_path": output_path.as_posix(),
        "semantic_manifest_checksum": checksum,
        "entity_count": len(entities),
        "metric_count": len(metrics),
        "join_count": len(joins),
    }


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []
