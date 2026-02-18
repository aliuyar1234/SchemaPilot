from __future__ import annotations

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
