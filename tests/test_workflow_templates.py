from __future__ import annotations

from pathlib import Path


def test_pack_and_connector_workflow_templates_exist() -> None:
    required = [
        Path(".github/workflow-templates/pack-validation.yml"),
        Path(".github/workflow-templates/connector-conformance.yml"),
    ]
    for path in required:
        assert path.exists(), f"Missing workflow template: {path.as_posix()}"
