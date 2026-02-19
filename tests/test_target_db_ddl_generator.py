from __future__ import annotations

from backend.shared_domain.target_db.ddl_generator import (
    generate_target_db_ddl,
    migration_drop_statements,
)
from backend.shared_domain.target_db.type_mapping import map_canonical_type


def _manifest(*, include_customer: bool) -> dict[str, object]:
    entities: list[dict[str, object]] = [
        {
            "entity_id": "invoice",
            "dataset_id": "dataset_invoices",
            "primary_key": "invoice_id",
            "attributes": ["customer_id", "invoice_date", "region"],
            "attribute_types": {
                "invoice_id": "string",
                "customer_id": "string",
                "invoice_date": "date",
                "region": "string",
            },
        }
    ]
    if include_customer:
        entities.append(
            {
                "entity_id": "customer",
                "dataset_id": "dataset_customers",
                "primary_key": "customer_id",
                "attributes": ["customer_name", "region"],
                "attribute_types": {
                    "customer_id": "string",
                    "customer_name": "string",
                    "region": "string",
                },
            }
        )
    return {
        "manifest_version": "1",
        "workspace_id": "ws_123",
        "entities": entities,
        "metrics": [],
        "joins": [],
    }


def test_generate_target_db_ddl_is_deterministic() -> None:
    manifest = _manifest(include_customer=True)
    first = generate_target_db_ddl(manifest=manifest, db_type="postgres", schema="gold")
    second = generate_target_db_ddl(manifest=manifest, db_type="postgres", schema="gold")
    assert first == second
    assert len(first) == 2
    assert first[0].startswith('CREATE TABLE IF NOT EXISTS "gold"."customer"')
    assert '"customer_id" TEXT NOT NULL' in first[0]
    assert first[1].startswith('CREATE TABLE IF NOT EXISTS "gold"."invoice"')
    assert '"invoice_date" DATE NULL' in first[1]


def test_migration_drop_statements_detect_removed_entities() -> None:
    previous_manifest = _manifest(include_customer=True)
    current_manifest = _manifest(include_customer=False)
    drops = migration_drop_statements(
        previous_manifest=previous_manifest,
        current_manifest=current_manifest,
        db_type="postgres",
        schema="gold",
    )
    assert drops == ['DROP TABLE IF EXISTS "gold"."customer"']


def test_map_canonical_type_resolves_per_engine() -> None:
    assert map_canonical_type("date", db_type="postgres") == "DATE"
    assert map_canonical_type("boolean", db_type="mysql") == "TINYINT(1)"
    assert map_canonical_type("json", db_type="sqlite") == "TEXT"

