"""Policy pack and permission templates for common deployment patterns."""

from __future__ import annotations

import json
from pathlib import Path


def load_policy_packs() -> list[dict[str, object]]:
    """Load bundled policy packs."""
    path = Path(__file__).with_name("policy_packs.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def list_policy_pack_summaries() -> list[dict[str, str]]:
    """Return compact policy pack metadata for UI/CLI discovery."""
    summaries: list[dict[str, str]] = []
    for item in load_policy_packs():
        summaries.append(
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
                "description": str(item.get("description", "")),
            }
        )
    return summaries


def find_policy_pack_template(pack_id: str) -> dict[str, object] | None:
    """Resolve a template actor payload from a policy pack id."""
    for item in load_policy_packs():
        if str(item.get("id", "")) != pack_id:
            continue
        template = item.get("template_actor")
        if isinstance(template, dict):
            return template
        return None
    return None
