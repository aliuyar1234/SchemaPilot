from __future__ import annotations

from backend.workers.pii import detect_pii_proposals


def test_pii_detection_proposal_emits_confidence_and_review_trigger() -> None:
    result = detect_pii_proposals("email", ["a@example.com", "b@example.com", "invalid"])
    assert result["tag"] == "email"
    assert isinstance(result["confidence"], float)
    assert result["review_required"] is True
