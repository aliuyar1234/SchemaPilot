from __future__ import annotations

from backend.control_plane.decision_engine import (
    DecisionInput,
    build_recommendation_report,
    evaluate_hard_constraints,
    load_templates,
    score_templates,
)


def test_template_library_contains_t1_to_t8_exactly() -> None:
    templates = load_templates()
    template_ids = [str(template["id"]) for template in templates]
    assert template_ids == ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]


def test_recommendation_report_has_required_sections() -> None:
    report = build_recommendation_report(
        {
            "strict_security": True,
            "needs_documents": True,
            "confidence_signal": 0.5,
            "evidence_completeness": 0.4,
        }
    )
    assert "ranked_templates" in report
    assert "hard_constraint_gates" in report
    assert "missing_evidence" in report
    assert "approval_required" in report
    assert isinstance(report["approval_reasons"], list)


def test_hard_constraints_gate_for_single_node_mode() -> None:
    templates = load_templates()
    gates = evaluate_hard_constraints(
        templates,
        DecisionInput(
            strict_security=False,
            on_prem_required=False,
            single_node_only=True,
            needs_documents=False,
            confidence_signal=0.5,
            evidence_completeness=0.5,
        ),
    )
    assert gates["T3"]["pass"] is False
    assert "single_node_only" in gates["T3"]["failures"]


def test_scoring_model_uses_weights() -> None:
    templates = load_templates()
    gates = evaluate_hard_constraints(
        templates,
        DecisionInput(
            strict_security=False,
            on_prem_required=False,
            single_node_only=False,
            needs_documents=False,
            confidence_signal=0.9,
            evidence_completeness=0.9,
        ),
    )
    ranking = score_templates(
        templates,
        gates,
        weights={"complexity": 1.0, "governance": 0.0, "documents": 0.0},
    )
    assert ranking[0]["template_id"] == "T1"


def test_confidence_and_approval_triggers() -> None:
    report = build_recommendation_report(
        {
            "strict_security": True,
            "needs_documents": True,
            "confidence_signal": 0.4,
            "evidence_completeness": 0.4,
        }
    )
    assert report["confidence"] < 0.75
    assert report["approval_required"] is True
