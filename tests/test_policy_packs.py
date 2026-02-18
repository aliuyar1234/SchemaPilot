from __future__ import annotations

from backend.shared_domain.policy_packs import (
    find_policy_pack_template,
    list_policy_pack_summaries,
    load_policy_packs,
)


def test_policy_packs_are_loadable() -> None:
    packs = load_policy_packs()
    assert len(packs) >= 3


def test_policy_pack_summary_contains_expected_id() -> None:
    summaries = list_policy_pack_summaries()
    assert any(item["id"] == "starter_local_team" for item in summaries)


def test_policy_pack_template_lookup() -> None:
    template = find_policy_pack_template("enterprise_ai_assistant")
    assert template is not None
    assert template["actor_type"] == "ai"
