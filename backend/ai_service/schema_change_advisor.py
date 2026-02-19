"""Proposal-only schema evolution advisor for target DB flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaAdvisorProposal:
    """Single proposal row for schema evolution review."""

    proposal_type: str
    entity_id: str
    field_name: str
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_type": self.proposal_type,
            "entity_id": self.entity_id,
            "field_name": self.field_name,
            "reason": self.reason,
            "confidence": self.confidence,
            "requires_approval": True,
            "auto_apply": False,
        }


def build_schema_evolution_proposals(
    *,
    semantic_manifest: dict[str, object] | None,
    observed_columns_by_entity: dict[str, list[str]],
) -> list[dict[str, object]]:
    """Generate deterministic proposal list without applying any change."""
    if not isinstance(semantic_manifest, dict):
        return []
    entities_raw = semantic_manifest.get("entities", [])
    entities = entities_raw if isinstance(entities_raw, list) else []
    known_by_entity: dict[str, set[str]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("entity_id", "")).strip()
        if not entity_id:
            continue
        fields = set()
        primary_key = str(entity.get("primary_key", "")).strip()
        if primary_key:
            fields.add(primary_key)
        attrs_raw = entity.get("attributes", [])
        if isinstance(attrs_raw, list):
            for field in attrs_raw:
                candidate = str(field).strip()
                if candidate:
                    fields.add(candidate)
        known_by_entity[entity_id] = fields

    proposals: list[SchemaAdvisorProposal] = []
    for entity_id in sorted(observed_columns_by_entity):
        observed = {
            str(column).strip()
            for column in observed_columns_by_entity.get(entity_id, [])
            if str(column).strip()
        }
        known = known_by_entity.get(entity_id, set())
        if not known:
            for column in sorted(observed):
                proposals.append(
                    SchemaAdvisorProposal(
                        proposal_type="entity_add_proposal",
                        entity_id=entity_id,
                        field_name=column,
                        reason="entity_not_in_semantic_manifest",
                        confidence=0.55,
                    )
                )
            continue
        for column in sorted(observed.difference(known)):
            proposals.append(
                SchemaAdvisorProposal(
                    proposal_type="field_add_proposal",
                    entity_id=entity_id,
                    field_name=column,
                    reason="observed_column_not_in_manifest",
                    confidence=0.65,
                )
            )
        for column in sorted(known.difference(observed)):
            proposals.append(
                SchemaAdvisorProposal(
                    proposal_type="field_deprecate_proposal",
                    entity_id=entity_id,
                    field_name=column,
                    reason="manifest_column_not_observed",
                    confidence=0.6,
                )
            )
    return [proposal.to_dict() for proposal in proposals]
