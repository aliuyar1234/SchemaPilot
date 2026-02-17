"""Decision engine for template ranking and recommendation reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class DecisionInput:
    """Normalized decision engine input payload."""

    strict_security: bool
    on_prem_required: bool
    single_node_only: bool
    needs_documents: bool
    confidence_signal: float
    evidence_completeness: float


def load_templates() -> list[dict[str, object]]:
    """Load fixed template library T1..T8."""
    path = Path(__file__).with_name("decision_templates.json")
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_hard_constraints(
    templates: list[dict[str, object]], input_data: DecisionInput
) -> dict[str, dict[str, object]]:
    """Evaluate hard constraints for each template."""
    gates: dict[str, dict[str, object]] = {}
    for template in templates:
        template_id = str(template["id"])
        components = _components(template)
        failures: list[str] = []
        if input_data.single_node_only and "trino" in components:
            failures.append("single_node_only")
        if (
            input_data.needs_documents
            and "opensearch" not in components
            and "qdrant" not in components
        ):
            failures.append("documents_required")
        if input_data.strict_security and "qdrant" in components:
            failures.append("strict_security_vector_review")
        gates[template_id] = {
            "pass": len(failures) == 0,
            "failures": failures,
        }
    return gates


def score_templates(
    templates: list[dict[str, object]],
    gates: dict[str, dict[str, object]],
    *,
    weights: dict[str, float],
) -> list[dict[str, object]]:
    """Score templates that pass hard constraints."""
    ranked: list[dict[str, object]] = []
    for template in templates:
        template_id = str(template["id"])
        gate = gates[template_id]
        if not bool(gate["pass"]):
            continue
        components = _components(template)
        complexity_score = 1.0 / max(len(components), 1)
        governance_score = 1.0 if "trino" in components else 0.6
        docs_score = 1.0 if ("opensearch" in components or "qdrant" in components) else 0.2
        total = (
            weights["complexity"] * complexity_score
            + weights["governance"] * governance_score
            + weights["documents"] * docs_score
        )
        ranked.append(
            {
                "template_id": template_id,
                "score": round(total, 4),
                "subscores": {
                    "complexity": round(complexity_score, 4),
                    "governance": round(governance_score, 4),
                    "documents": round(docs_score, 4),
                },
            }
        )
    return sorted(ranked, key=lambda item: cast(float, item["score"]), reverse=True)


def build_recommendation_report(intent: dict[str, object]) -> dict[str, object]:
    """Generate recommendation report payload."""
    templates = load_templates()
    decision_input = DecisionInput(
        strict_security=bool(intent.get("strict_security", False)),
        on_prem_required=bool(intent.get("on_prem_required", False)),
        single_node_only=bool(intent.get("single_node_only", False)),
        needs_documents=bool(intent.get("needs_documents", False)),
        confidence_signal=_parse_float(intent.get("confidence_signal", 0.5), default=0.5),
        evidence_completeness=_parse_float(intent.get("evidence_completeness", 0.5), default=0.5),
    )
    gates = evaluate_hard_constraints(templates, decision_input)
    weights = {
        "complexity": _parse_float(intent.get("weight_complexity", 0.5), default=0.5),
        "governance": _parse_float(intent.get("weight_governance", 0.3), default=0.3),
        "documents": _parse_float(intent.get("weight_documents", 0.2), default=0.2),
    }
    ranked = score_templates(templates, gates, weights=weights)
    confidence = max(
        0.0, min(1.0, (decision_input.confidence_signal + decision_input.evidence_completeness) / 2)
    )
    missing_evidence: list[str] = []
    if decision_input.evidence_completeness < 0.8:
        missing_evidence.append("query_workload_evidence")
    if not decision_input.on_prem_required:
        missing_evidence.append("deployment_constraints_confirmation")

    top_components = []
    if ranked:
        top_template_id = ranked[0]["template_id"]
        top_template = next(item for item in templates if item["id"] == top_template_id)
        top_components = sorted(_components(top_template))
    approval_reasons: list[str] = []
    if confidence < 0.75:
        approval_reasons.append("confidence_below_threshold")
    if len(top_components) > 3:
        approval_reasons.append("adds_store_complexity")
    if decision_input.strict_security and (
        "qdrant" in top_components or "opensearch" in top_components
    ):
        approval_reasons.append("strict_security_new_exposure")

    return {
        "ranked_templates": ranked,
        "hard_constraint_gates": gates,
        "confidence": round(confidence, 4),
        "missing_evidence": missing_evidence,
        "approval_required": len(approval_reasons) > 0,
        "approval_reasons": approval_reasons,
    }


def _components(template: dict[str, object]) -> set[str]:
    raw = template.get("components", [])
    if not isinstance(raw, list):
        return set()
    return {str(component) for component in raw}


def _parse_float(value: Any, *, default: float) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    return default
