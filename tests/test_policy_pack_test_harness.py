from __future__ import annotations

from pathlib import Path

from tools.policy_pack_test import main as policy_pack_test_main


def test_policy_pack_test_harness_passes_default_catalog(monkeypatch, tmp_path: Path) -> None:
    policy_file = tmp_path / "policy_packs.json"
    policy_file.write_text(
        """
[
  {
    "id": "pack_a",
    "template_actor": {
      "actor_type": "human",
      "roles": ["analyst"],
      "attributes": {}
    }
  }
]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["policy_pack_test.py", "--file", policy_file.as_posix()],
    )
    assert policy_pack_test_main() == 0
