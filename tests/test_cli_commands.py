from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from cli.schemapilot_cli.main import app

runner = CliRunner()


def test_connect_command_calls_control_plane(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return {"source_id": "s1"}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "connect",
            "filesystem",
            "--workspace",
            "w1",
            "--root",
            "/tmp/data",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://cp/api/v1/workspaces/w1/sources"
    assert captured["payload"]["source_type"] == "filesystem"
    assert captured["payload"]["scope"]["root_path"] == "/tmp/data"


def test_onboard_demo_command_calls_bootstrap_endpoint(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return {"workspace": {"workspace_id": "w-demo"}}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "onboard-demo",
            "--workspace-name",
            "Acme Demo",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://cp/api/v1/onboarding/demo_bootstrap"
    assert captured["payload"]["workspace_name"] == "Acme Demo"


def test_run_command_calls_control_plane(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return {"run_id": "r1", "status": "queued"}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        ["run", "--workspace", "w1", "--type", "profile", "--api-base-url", "http://cp"],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://cp/api/v1/workspaces/w1/runs"
    assert captured["payload"]["run_type"] == "profile"


def test_status_command_reads_tasks_and_summary(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        calls.append((method, url))
        if url.endswith("/review_tasks"):
            return [{"task_id": "t1"}, {"task_id": "t2"}]
        if url.endswith("/review_tasks/summary"):
            return {"total_tasks": 2, "blocking_open_tasks": 1}
        return {}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        ["status", "--workspace", "w1", "--api-base-url", "http://cp"],
    )
    assert result.exit_code == 0
    assert ("GET", "http://cp/api/v1/workspaces/w1/review_tasks") in calls
    assert ("GET", "http://cp/api/v1/workspaces/w1/review_tasks/summary") in calls
    assert '"review_task_count": 2' in result.stdout
    assert '"blocking_open_tasks": 1' in result.stdout


def test_kpi_report_invokes_tracker_script(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], *, cwd=None):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = cwd

    monkeypatch.setattr("cli.schemapilot_cli.main._run", fake_run)
    result = runner.invoke(
        app,
        [
            "kpi-report",
            "--week",
            "2026-W08",
            "--ttfsa-minutes",
            "25",
            "--install-success-rate",
            "0.91",
            "--security-regressions",
            "0",
            "--deterministic-pass-rate",
            "1.0",
            "--active-contributors",
            "5",
            "--issue-response-hours",
            "12",
        ],
    )
    assert result.exit_code == 0
    command = captured["command"]
    assert "tools/kpi_tracker.py" in command
    assert "--week" in command
    assert "2026-W08" in command


def test_migrate_up_invokes_alembic_upgrade_head(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], *, cwd=None):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = cwd

    monkeypatch.setattr("cli.schemapilot_cli.main._run", fake_run)
    result = runner.invoke(
        app,
        ["migrate-up", "--alembic-ini", "custom.ini"],
    )
    assert result.exit_code == 0
    command = captured["command"]
    assert command[1:] == ["-m", "alembic", "-c", "custom.ini", "upgrade", "head"]


def test_migrate_status_invokes_alembic_current(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], *, cwd=None):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = cwd

    monkeypatch.setattr("cli.schemapilot_cli.main._run", fake_run)
    result = runner.invoke(
        app,
        ["migrate-status", "--alembic-ini", "custom.ini"],
    )
    assert result.exit_code == 0
    command = captured["command"]
    assert command[1:] == ["-m", "alembic", "-c", "custom.ini", "current"]


def test_templates_list_shows_expected_packs() -> None:
    result = runner.invoke(app, ["templates", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["packs"] == ["crm", "invoices", "support"]


def test_templates_apply_generates_bundle(tmp_path: Path) -> None:
    output_root = tmp_path / "gold_templates"
    result = runner.invoke(
        app,
        [
            "templates",
            "apply",
            "invoices",
            "--workspace",
            "workspace-a",
            "--output-root",
            output_root.as_posix(),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["pack_id"] == "invoices"
    output_path = Path(payload["output_path"])
    assert output_path.exists()


def test_plugins_scaffold_generates_connector_package(tmp_path: Path) -> None:
    output_root = tmp_path / "generated_plugins"
    result = runner.invoke(
        app,
        [
            "plugins",
            "scaffold",
            "--name",
            "acme_connector",
            "--output-root",
            output_root.as_posix(),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    package_root = Path(payload["package_root"])
    assert package_root.exists()
    assert (package_root / "pyproject.toml").exists()
    assert (package_root / "acme_connector" / "connector.py").exists()
    assert (package_root / "tests" / "test_connector.py").exists()


def test_catalog_export_writes_snapshot_file(monkeypatch, tmp_path: Path) -> None:
    snapshot = {
        "snapshot_version": "v1",
        "workspace": {"workspace_id": "w1"},
        "sources": [],
        "datasets": [],
    }

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        assert method == "GET"
        assert url.endswith("/api/v1/workspaces/w1/catalog/export")
        _ = payload
        return snapshot

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    output_path = tmp_path / "snapshot.json"
    result = runner.invoke(
        app,
        [
            "catalog-export",
            "--workspace",
            "w1",
            "--output",
            output_path.as_posix(),
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["snapshot_version"] == "v1"


def test_catalog_import_reads_file_and_posts_payload(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return {"workspace_id": "w1", "imported_sources": 1, "imported_datasets": 0}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps({"snapshot_version": "v1", "workspace": {"workspace_id": "w1"}}),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "catalog-import",
            "--workspace",
            "w1",
            "--input",
            snapshot_path.as_posix(),
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/v1/workspaces/w1/catalog/import")
    assert "snapshot" in captured["payload"]


def test_demo_generate_writes_deterministic_files(tmp_path: Path) -> None:
    output_root = tmp_path / "demo_bundle"
    result = runner.invoke(
        app,
        [
            "demo-generate",
            "--output-root",
            output_root.as_posix(),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    manifest_path = Path(str(payload["manifest_path"]))
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario_version"] == "v1"
    assert manifest["exports"] == ["customers.csv", "invoices.csv", "tickets.csv"]
