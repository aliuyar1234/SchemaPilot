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


def test_target_db_create_calls_control_plane(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return {"target_db": {"target_db_id": "tdb1"}}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "target-db",
            "create",
            "--workspace",
            "w1",
            "--name",
            "serving-db",
            "--type",
            "postgres",
            "--mode",
            "managed",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://cp/api/v1/workspaces/w1/target-dbs"
    assert captured["payload"]["db_type"] == "postgres"


def test_target_db_validate_waits_for_run(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        calls.append((method, url, payload))
        if url.endswith("/validate"):
            return {"run_id": "run-target-db-1"}
        if "/runs/" in url:
            return {"run_id": "run-target-db-1", "status": "succeeded"}
        return {}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "target-db",
            "validate",
            "--workspace",
            "w1",
            "--target-db",
            "tdb1",
            "--wait",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert (
        "POST",
        "http://cp/api/v1/workspaces/w1/target-dbs/tdb1/validate",
        {"strict": True},
    ) in calls
    assert (
        "GET",
        "http://cp/api/v1/workspaces/w1/runs/run-target-db-1",
        None,
    ) in calls


def test_target_db_index_plan_calls_control_plane(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        if method == "POST":
            return {"run_id": "run-index-1"}
        return {"run_id": "run-index-1", "status": "succeeded"}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "target-db",
            "index-plan",
            "--workspace",
            "w1",
            "--target-db",
            "tdb1",
            "--build",
            "b1",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://cp/api/v1/workspaces/w1/target-dbs/tdb1/indexes/plan"
    assert captured["payload"]["target_build_id"] == "b1"


def test_target_db_cutover_calls_control_plane(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return {"state": {"active_target_db_id": "tdb-shadow"}}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "target-db",
            "cutover",
            "--workspace",
            "w1",
            "--to-target-db",
            "tdb-shadow",
            "--from-target-db",
            "tdb-primary",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://cp/api/v1/workspaces/w1/target-dbs/cutover"
    assert captured["payload"]["to_target_db_id"] == "tdb-shadow"
    assert captured["payload"]["from_target_db_id"] == "tdb-primary"


def test_target_db_sync_schedule_create_calls_control_plane(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return {"schedule_id": "sched_1"}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "target-db",
            "sync-schedule-create",
            "--workspace",
            "w1",
            "--target-db",
            "tdb1",
            "--schedule",
            "*/10 * * * *",
            "--datasets",
            "ds_a,ds_b",
            "--max-runtime-seconds",
            "120",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert (
        captured["url"]
        == "http://cp/api/v1/workspaces/w1/target-dbs/tdb1/sync/schedules"
    )
    assert captured["payload"]["datasets"] == ["ds_a", "ds_b"]
    assert captured["payload"]["max_runtime_seconds"] == 120


def test_target_db_generic_plan_command_calls_expected_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        if method == "POST":
            return {"run_id": "run-plan-1"}
        return {"run_id": "run-plan-1", "status": "succeeded"}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "target-db",
            "plan",
            "--workspace",
            "w1",
            "--target-db",
            "tdb1",
            "--kind",
            "index",
            "--payload",
            "{\"target_build_id\":\"b1\"}",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["url"] == "http://cp/api/v1/workspaces/w1/target-dbs/tdb1/indexes/plan"
    assert captured["payload"]["target_build_id"] == "b1"


def test_target_db_generic_apply_command_calls_expected_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        if method == "POST":
            return {"run_id": "run-apply-1"}
        return {"run_id": "run-apply-1", "status": "succeeded"}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "target-db",
            "apply",
            "--workspace",
            "w1",
            "--target-db",
            "tdb1",
            "--kind",
            "rls",
            "--plan-id",
            "plan1",
            "--expected-checksum",
            "sha256:123",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert captured["url"] == "http://cp/api/v1/workspaces/w1/target-dbs/tdb1/rls/apply"
    assert captured["payload"]["plan_id"] == "plan1"


def test_doctor_command_returns_ok_report_for_valid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "doctor.json"
    config_path.write_text(
        json.dumps(
            {
                "profile": "starter",
                "bind_address": "127.0.0.1",
                "auth_mode": "local",
                "database_url": f"sqlite:///{(tmp_path / 'doctor.db').as_posix()}",
                "storage_root": (tmp_path / "storage").as_posix(),
                "secrets_store_backend": "local_encrypted",
                "secrets_store_root": (tmp_path / "secrets").as_posix(),
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["doctor", "--config", config_path.as_posix()])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"


def test_doctor_command_fails_for_invalid_config_key(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text(json.dumps({"unknown_key": "x"}), encoding="utf-8")
    result = runner.invoke(app, ["doctor", "--config", config_path.as_posix()])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"


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


def test_init_interactive_bootstraps_workspace_source_and_run(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        calls.append((method, url, payload))
        if url.endswith("/api/v1/workspaces"):
            return {"workspace_id": "w-interactive"}
        if url.endswith("/sources"):
            return {"source_id": "s-interactive"}
        if url.endswith("/runs"):
            return {"run_id": "r-interactive", "status": "queued"}
        return {}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        ["init-interactive", "--api-base-url", "http://cp"],
        input="Acme Workspace\nfilesystem\n/tmp/exports\n",
    )
    assert result.exit_code == 0
    assert calls[0][0] == "POST"
    assert calls[0][1] == "http://cp/api/v1/workspaces"
    assert calls[1][1] == "http://cp/api/v1/workspaces/w-interactive/sources"
    assert calls[2][1] == "http://cp/api/v1/workspaces/w-interactive/runs"


def test_init_interactive_waits_and_generates_template_bundle(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        calls.append((method, url, payload))
        if url.endswith("/api/v1/workspaces"):
            return {"workspace_id": "w-init"}
        if url.endswith("/sources"):
            return {"source_id": "s-init"}
        if url.endswith("/runs"):
            return {"run_id": "r-init", "status": "queued"}
        return {}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    monkeypatch.setattr(
        "cli.schemapilot_cli.main._wait_for_run_completion",
        lambda **kwargs: {"run_id": kwargs["run_id"], "status": "succeeded"},
    )
    output_root = tmp_path / "template_out"
    result = runner.invoke(
        app,
        [
            "init-interactive",
            "--api-base-url",
            "http://cp",
            "--template-pack",
            "invoices",
            "--template-output-root",
            output_root.as_posix(),
            "--wait-for-run",
        ],
        input="Init Workspace\nfilesystem\n/tmp/exports\n",
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout[result.stdout.find("{") :])
    assert payload["workspace_id"] == "w-init"
    assert payload["run_observed"]["status"] == "succeeded"
    assert payload["template_bundle"]["pack_id"] == "invoices"
    assert Path(payload["template_bundle"]["output_path"]).exists()


def test_first_hour_command_bootstraps_demo_workspace(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        calls.append((method, url, payload))
        if url.endswith("/api/v1/workspaces"):
            return {"workspace_id": "w-first-hour"}
        if url.endswith("/sources"):
            return {"source_id": "s-first-hour"}
        if url.endswith("/runs"):
            return {"run_id": "r-first-hour", "status": "queued"}
        if "/runs/" in url:
            return {"run_id": "r-first-hour", "status": "succeeded"}
        return {}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    demo_root = tmp_path / "demo"
    template_root = tmp_path / "templates"
    result = runner.invoke(
        app,
        [
            "first-hour",
            "--workspace-name",
            "First Hour Test",
            "--api-base-url",
            "http://cp",
            "--gateway-base-url",
            "http://gw",
            "--output-root",
            demo_root.as_posix(),
            "--template-output-root",
            template_root.as_posix(),
            "--template-pack",
            "invoices",
            "--wait-for-run",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["workspace_id"] == "w-first-hour"
    assert payload["source"]["source_id"] == "s-first-hour"
    assert payload["run"]["run_id"] == "r-first-hour"
    assert payload["run_observed"]["status"] == "succeeded"
    assert payload["template_bundle"]["pack_id"] == "invoices"
    assert Path(payload["template_bundle"]["output_path"]).exists()
    assert Path(payload["demo_data"]["manifest_path"]).exists()
    assert any("schemapilot query" in step for step in payload["next_steps"])
    assert calls[0][0] == "POST"
    assert calls[0][1] == "http://cp/api/v1/workspaces"


def test_init_preset_dropzone_bootstraps_workspace_source_and_run(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        calls.append((method, url, payload))
        if url.endswith("/api/v1/workspaces"):
            return {"workspace_id": "w-preset"}
        if url.endswith("/sources"):
            return {"source_id": "s-preset", "scope": payload.get("scope", {})}
        if url.endswith("/runs"):
            return {"run_id": "r-preset", "status": "queued"}
        if "/runs/" in url:
            return {"run_id": "r-preset", "status": "succeeded"}
        return {}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "init-preset",
            "--preset",
            "dropzone-team",
            "--api-base-url",
            "http://cp",
            "--output-root",
            (tmp_path / "demo").as_posix(),
            "--wait-for-run",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["workspace_id"] == "w-preset"
    assert payload["source"]["source_id"] == "s-preset"
    assert payload["run_observed"]["status"] == "succeeded"
    assert calls[1][2] is not None
    scope = calls[1][2]["scope"]  # type: ignore[index]
    assert scope["root_path"]
    assert isinstance(scope.get("required_files"), list)


def test_init_preset_sharepoint_uses_sharepoint_source_type(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        calls.append((method, url, payload))
        if url.endswith("/api/v1/workspaces"):
            return {"workspace_id": "w-sharepoint"}
        if url.endswith("/sources"):
            return {"source_id": "s-sharepoint", "scope": payload.get("scope", {})}
        if url.endswith("/runs"):
            return {"run_id": "r-sharepoint", "status": "queued"}
        if "/runs/" in url:
            return {"run_id": "r-sharepoint", "status": "succeeded"}
        return {}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "init-preset",
            "--preset",
            "sharepoint-team",
            "--api-base-url",
            "http://cp",
            "--source-root",
            "/sites/team/shared-documents",
            "--wait-for-run",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["workspace_id"] == "w-sharepoint"
    assert payload["source"]["source_id"] == "s-sharepoint"
    assert payload["run_observed"]["status"] == "succeeded"
    assert calls[1][2] is not None
    source_payload = calls[1][2]
    assert source_payload["source_type"] == "sharepoint"  # type: ignore[index]
    assert source_payload["scope"]["root_path"] == "/sites/team/shared-documents"  # type: ignore[index]


def test_init_preset_rejects_unknown_preset() -> None:
    result = runner.invoke(app, ["init-preset", "--preset", "unknown-preset"])
    assert result.exit_code == 1
    assert "Unsupported preset" in (result.stdout + result.stderr)


def test_review_batch_requires_confirmation(monkeypatch) -> None:
    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = (method, url, payload, auth_token)
        return []

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "review-batch",
            "--workspace",
            "w1",
            "--decision",
            "approve",
            "--task-id",
            "t1",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 1
    assert "Batch decisions require --confirm YES." in (result.stdout + result.stderr)


def test_review_batch_all_open_applies_decision(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = auth_token
        calls.append((method, url, payload))
        if url.endswith("/review_tasks"):
            return [{"task_id": "t2", "status": "open"}, {"task_id": "t1", "status": "open"}]
        return {"status": "done"}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "review-batch",
            "--workspace",
            "w1",
            "--decision",
            "approve",
            "--all-open",
            "--confirm",
            "YES",
            "--api-base-url",
            "http://cp",
        ],
    )
    assert result.exit_code == 0
    assert ("GET", "http://cp/api/v1/workspaces/w1/review_tasks", None) in calls
    assert (
        "POST",
        "http://cp/api/v1/workspaces/w1/review_tasks/t1/decision",
        {"decision": "approve", "reason": "batch_cli_decision"},
    ) in calls
    assert (
        "POST",
        "http://cp/api/v1/workspaces/w1/review_tasks/t2/decision",
        {"decision": "approve", "reason": "batch_cli_decision"},
    ) in calls


def test_query_command_formats_output_and_exports_json(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        captured["auth_token"] = auth_token
        return {
            "result": {
                "columns": [{"name": "one", "type": "INTEGER"}],
                "rows": [[1]],
                "row_count": 1,
            },
            "provenance": {"provenance_version": "1", "citations": []},
            "request_id": "req-1",
        }

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    export_path = tmp_path / "query.json"
    result = runner.invoke(
        app,
        [
            "query",
            "--workspace",
            "w1",
            "--sql",
            "select 1 as one",
            "--dataset-id",
            "dataset-1",
            "--gateway-base-url",
            "http://gw",
            "--export",
            export_path.as_posix(),
            "--export-format",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://gw/api/v1/gateway/query"
    assert captured["payload"]["resource_attributes"]["dataset_id"] == "dataset-1"
    assert export_path.exists()
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["provenance"]["provenance_version"] == "1"


def test_query_templates_command_lists_templates() -> None:
    result = runner.invoke(app, ["query-templates"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    template_ids = [item["template_id"] for item in payload["templates"]]
    assert "invoice_count" in template_ids


def test_query_template_run_renders_and_executes(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        captured["auth_token"] = auth_token
        return {
            "result": {"columns": [{"name": "invoice_count", "type": "INTEGER"}], "rows": [[1]]},
            "provenance": {"provenance_version": "1"},
            "request_id": "req-template",
        }

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "query-template-run",
            "--workspace",
            "w1",
            "--template-id",
            "invoice_count",
            "--params-json",
            '{"table_name":"silver.invoice"}',
            "--gateway-base-url",
            "http://gw",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://gw/api/v1/gateway/query"
    query_payload = captured["payload"]
    assert query_payload["template_id"] == "invoice_count"
    assert "silver.invoice" in query_payload["query"]["text"]


def test_policy_simulate_calls_gateway_endpoint(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        captured["auth_token"] = auth_token
        return {"result": "allow", "reason": "allow", "applied_masks": {}, "applied_filters": {}}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    result = runner.invoke(
        app,
        [
            "policy-simulate",
            "--workspace",
            "w1",
            "--actor-roles",
            "data_steward,analyst",
            "--actor-attributes",
            '{"allowed_dataset_ids":["dataset-1"]}',
            "--resource-attributes",
            '{"dataset_id":"dataset-1"}',
            "--gateway-base-url",
            "http://gw",
        ],
    )
    assert result.exit_code == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://gw/api/v1/gateway/policy/simulate"
    assert captured["payload"]["actor"]["roles"] == ["data_steward", "analyst"]


def test_policy_audit_report_generates_output_file(monkeypatch, tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios.json"
    scenario_path.write_text(
        json.dumps(
            [
                {
                    "id": "scenario-1",
                    "actor": {"actor_type": "human", "roles": ["data_steward"], "attributes": {}},
                    "resource_attributes": {"dataset_id": "dataset-1"},
                    "action": "query",
                }
            ]
        ),
        encoding="utf-8",
    )

    def fake_request_json(method: str, url: str, payload=None, *, auth_token=None):  # type: ignore[no-untyped-def]
        _ = (method, url, payload, auth_token)
        return {"result": "allow", "reason": "allow", "applied_masks": {}, "applied_filters": {}}

    monkeypatch.setattr("cli.schemapilot_cli.main._request_json", fake_request_json)
    output_path = tmp_path / "audit_report.json"
    result = runner.invoke(
        app,
        [
            "policy-audit-report",
            "--workspace",
            "w1",
            "--scenarios",
            scenario_path.as_posix(),
            "--output",
            output_path.as_posix(),
            "--gateway-base-url",
            "http://gw",
        ],
    )
    assert result.exit_code == 0
    assert output_path.exists()
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["scenario_count"] == 1
    assert report["scenarios"][0]["id"] == "scenario-1"


def test_policy_diff_command_generates_deterministic_output(tmp_path: Path) -> None:
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_path.write_text(
        json.dumps(
            {
                "workspace_id": "w1",
                "scenario_count": 1,
                "scenarios": [
                    {
                        "id": "scenario-1",
                        "result": "allow",
                        "reason": "allow",
                        "applied_masks": {"email": "hash"},
                        "applied_filters": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    after_path.write_text(
        json.dumps(
            {
                "workspace_id": "w1",
                "scenario_count": 1,
                "scenarios": [
                    {
                        "id": "scenario-1",
                        "result": "deny",
                        "reason": "policy_denied",
                        "applied_masks": {"email": "redact"},
                        "applied_filters": {"workspace_id": "w1"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "policy_diff.json"
    result = runner.invoke(
        app,
        [
            "policy-diff",
            "--before",
            before_path.as_posix(),
            "--after",
            after_path.as_posix(),
            "--output",
            output_path.as_posix(),
        ],
    )
    assert result.exit_code == 0
    assert output_path.exists()
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "changed"
    assert report["summary"]["result_change_count"] == 1
    assert report["summary"]["mask_change_count"] == 1
