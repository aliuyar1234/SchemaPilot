"""SchemaPilot CLI entrypoint."""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Mapping
from pathlib import Path
from urllib import error as urlerror
from urllib.parse import urlparse

import typer

from cli.schemapilot_cli.analyze import analyze_workspace
from cli.schemapilot_cli.diag import generate_diag_bundle
from cli.schemapilot_cli.doctor import run_doctor_preflight
from backend.shared_domain.demo_scenario import generate_demo_scenario
from backend.shared_domain.gold_templates import (
    generate_gold_template_bundle,
    list_gold_template_packs,
)
from backend.shared_domain.ids import new_ulid

app = typer.Typer(help="SchemaPilot CLI")
templates_app = typer.Typer(help="Gold template pack commands")
plugins_app = typer.Typer(help="Plugin SDK helper commands")
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_CP_AUTH_TOKEN = os.getenv("SCHEMAPILOT_CP_TOKEN", "local-platform-admin-token")
DEFAULT_GATEWAY_AUTH_TOKEN = os.getenv("SCHEMAPILOT_GATEWAY_TOKEN", "local-analyst-token")
DEFAULT_DATABASE_URL = os.getenv("SCHEMAPILOT_DATABASE_URL", "sqlite:///./runtime/schemapilot.db")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    typer.echo("$ " + " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def _request_json(
    method: str,
    url: str,
    payload: Mapping[str, object] | None = None,
    *,
    auth_token: str | None = None,
) -> dict[str, object] | list[dict[str, object]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        typer.echo(f"Unsupported URL scheme for API request: {parsed.scheme}", err=True)
        raise typer.Exit(code=1)
    if not parsed.hostname:
        typer.echo(f"Missing hostname in API URL: {url}", err=True)
        raise typer.Exit(code=1)
    body = json.dumps(dict(payload)).encode("utf-8") if payload is not None else None
    connection_cls = (
        http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_cls(parsed.hostname, parsed.port, timeout=15)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    headers = {"Accept": "application/json"}
    resolved_token = (auth_token if auth_token is not None else DEFAULT_CP_AUTH_TOKEN).strip()
    if resolved_token:
        headers["Authorization"] = f"Bearer {resolved_token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method.upper(), path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read().decode("utf-8", errors="ignore")
        if response.status >= 400:
            typer.echo(f"HTTP {response.status} {method} {url}: {raw}", err=True)
            raise typer.Exit(code=1)
        if not raw:
            return {}
        parsed_body = json.loads(raw)
        if isinstance(parsed_body, list):
            return [item for item in parsed_body if isinstance(item, dict)]
        if isinstance(parsed_body, dict):
            return parsed_body
        return {}
    except (OSError, urlerror.URLError, TimeoutError) as exc:  # pragma: no cover
        typer.echo(f"Request failed for {method} {url}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        connection.close()


def _as_dict(payload: dict[str, object] | list[dict[str, object]]) -> dict[str, object]:
    return payload if isinstance(payload, dict) else {}


@app.command()
def doctor(
    config_path: str | None = typer.Option(
        None, "--config", help="Optional config file path (.json/.yaml)."
    ),
) -> None:
    """Run environment preflight checks."""
    report = run_doctor_preflight(config_path=config_path)
    typer.echo(json.dumps(report, indent=2, sort_keys=True))
    if str(report.get("status", "fail")) != "ok":
        raise typer.Exit(code=1)


@app.command()
def init(
    profile: str = "team",
    interactive: bool = typer.Option(False, "--interactive/--no-interactive"),
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
    run_discover: bool = typer.Option(True, "--run-discover/--no-run-discover"),
) -> None:
    """Generate local config skeleton."""
    if interactive:
        init_interactive(api_base_url=api_base_url, profile=profile, run_discover=run_discover)
        return
    config = {
        "profile": profile,
        "bind_address": "127.0.0.1",
        "auth_mode": "local",
        "database_url": "sqlite:///./runtime/schemapilot.db",
        "storage_root": "./runtime/storage",
        "credentials_ref_note": "store secret refs only, never plaintext secrets",
    }
    Path("runtime").mkdir(parents=True, exist_ok=True)
    output = Path("runtime/config.json")
    output.write_text(json.dumps(config, indent=2), encoding="utf-8")
    typer.echo(f"init: wrote {output.as_posix()}")


@app.command("init-interactive")
def init_interactive(
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
    profile: str = typer.Option("team", "--profile"),
    run_discover: bool = typer.Option(True, "--run-discover/--no-run-discover"),
) -> None:
    """Interactive onboarding: workspace + source + optional discover run."""
    workspace_name = typer.prompt("Workspace name", default="Team Workspace").strip()
    source_type = typer.prompt("Source type", default="filesystem").strip().lower()
    source_root = typer.prompt("Source root path", default="./runtime/demo/first_hour/exports").strip()
    if not workspace_name:
        typer.echo("Workspace name is required.", err=True)
        raise typer.Exit(code=1)
    if not source_type:
        typer.echo("Source type is required.", err=True)
        raise typer.Exit(code=1)
    if not source_root:
        typer.echo("Source root path is required.", err=True)
        raise typer.Exit(code=1)

    workspace_response = _request_json(
        "POST",
        f"{api_base_url}/api/v1/workspaces",
        {"name": workspace_name, "profile": profile, "security_baseline": "strict"},
    )
    workspace_id = str(_as_dict(workspace_response).get("workspace_id", "")).strip()
    if not workspace_id:
        typer.echo("Workspace creation did not return workspace_id.", err=True)
        raise typer.Exit(code=1)

    source_response = _request_json(
        "POST",
        f"{api_base_url}/api/v1/workspaces/{workspace_id}/sources",
        {
            "source_type": source_type,
            "scope": {"root_path": source_root},
            "display_name": source_root,
        },
    )
    run_response: dict[str, object] = {}
    if run_discover:
        run_payload = _request_json(
            "POST",
            f"{api_base_url}/api/v1/workspaces/{workspace_id}/runs",
            {"run_type": "discover"},
        )
        run_response = _as_dict(run_payload)

    typer.echo(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "source": _as_dict(source_response),
                "run": run_response,
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command()
def connect(
    source: str,
    workspace: str = typer.Option(..., "--workspace", "-w"),
    root: str | None = typer.Option(None, "--root"),
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
) -> None:
    """Register a source in the control plane."""
    scope: dict[str, object] = {}
    if root:
        scope["root_path"] = root
    payload = {
        "source_type": source,
        "scope": scope,
        "display_name": root or source,
    }
    response = _request_json(
        "POST", f"{api_base_url}/api/v1/workspaces/{workspace}/sources", payload
    )
    typer.echo(json.dumps(response, indent=2, sort_keys=True))


@app.command("onboard-demo")
def onboard_demo(
    workspace_name: str = typer.Option("Demo Workspace", "--workspace-name"),
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
) -> None:
    """Bootstrap a demo workspace from raw files to first governed query."""
    response = _request_json(
        "POST",
        f"{api_base_url}/api/v1/onboarding/demo_bootstrap",
        {"workspace_name": workspace_name},
    )
    typer.echo(json.dumps(response, indent=2, sort_keys=True))


@app.command()
def run(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    type: str = typer.Option("discover", "--type"),  # noqa: A002
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
) -> None:
    """Create a control-plane run."""
    payload = {"run_type": type}
    response = _request_json("POST", f"{api_base_url}/api/v1/workspaces/{workspace}/runs", payload)
    typer.echo(json.dumps(response, indent=2, sort_keys=True))


@app.command()
def status(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    run_id: str | None = typer.Option(None, "--run-id"),
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
) -> None:
    """Show review queue status or a specific run."""
    if run_id:
        response = _request_json(
            "GET", f"{api_base_url}/api/v1/workspaces/{workspace}/runs/{run_id}"
        )
        typer.echo(json.dumps(response, indent=2, sort_keys=True))
        return
    tasks = _request_json("GET", f"{api_base_url}/api/v1/workspaces/{workspace}/review_tasks")
    summary = _request_json(
        "GET", f"{api_base_url}/api/v1/workspaces/{workspace}/review_tasks/summary"
    )
    payload: dict[str, object] = {
        "workspace_id": workspace,
        "review_task_count": len(tasks) if isinstance(tasks, list) else 0,
        "review_tasks": tasks,
        "summary": _as_dict(summary),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("review-batch")
def review_batch(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    decision: str = typer.Option(..., "--decision"),
    reason: str = typer.Option("batch_cli_decision", "--reason"),
    all_open: bool = typer.Option(False, "--all-open"),
    task_id: list[str] = typer.Option([], "--task-id"),
    confirm: str = typer.Option("", "--confirm"),
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
) -> None:
    """Apply a guarded batch decision to review tasks."""
    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approve", "reject", "defer"}:
        typer.echo("Decision must be one of approve/reject/defer.", err=True)
        raise typer.Exit(code=1)
    selected_task_ids = [item.strip() for item in task_id if item.strip()]
    if all_open:
        tasks_response = _request_json("GET", f"{api_base_url}/api/v1/workspaces/{workspace}/review_tasks")
        tasks = tasks_response if isinstance(tasks_response, list) else []
        selected_task_ids = [
            str(task.get("task_id", ""))
            for task in tasks
            if isinstance(task, dict) and str(task.get("status", "")).lower() == "open"
        ]
    if not selected_task_ids:
        typer.echo("No tasks selected. Use --task-id or --all-open.", err=True)
        raise typer.Exit(code=1)
    if confirm.strip().upper() != "YES":
        typer.echo("Batch decisions require --confirm YES.", err=True)
        raise typer.Exit(code=1)
    if len(selected_task_ids) > 50:
        typer.echo("Batch decision exceeds safety cap of 50 tasks.", err=True)
        raise typer.Exit(code=1)

    applied: list[dict[str, object]] = []
    for task_id_value in sorted(set(selected_task_ids)):
        result = _request_json(
            "POST",
            f"{api_base_url}/api/v1/workspaces/{workspace}/review_tasks/{task_id_value}/decision",
            {"decision": normalized_decision, "reason": reason},
        )
        applied.append({"task_id": task_id_value, "result": _as_dict(result)})
    typer.echo(
        json.dumps(
            {
                "workspace_id": workspace,
                "decision": normalized_decision,
                "applied_count": len(applied),
                "applied": applied,
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command("query")
def query_console(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    sql: str = typer.Option(..., "--sql"),
    dataset_id: str | None = typer.Option(None, "--dataset-id"),
    max_rows: int = typer.Option(100, "--max-rows"),
    gateway_base_url: str = typer.Option(DEFAULT_GATEWAY_BASE_URL, "--gateway-base-url"),
    export_path: str | None = typer.Option(None, "--export"),
    export_format: str = typer.Option("json", "--export-format"),
) -> None:
    """Run one governed gateway SQL query and print provenance summary."""
    payload: dict[str, object] = {
        "workspace_id": workspace,
        "query": {"language": "sql", "text": sql},
        "max_rows": max(max_rows, 1),
    }
    if dataset_id:
        payload["resource_attributes"] = {"dataset_id": dataset_id}
    response = _request_json(
        "POST",
        f"{gateway_base_url}/api/v1/gateway/query",
        payload,
        auth_token=DEFAULT_GATEWAY_AUTH_TOKEN,
    )
    result = _as_dict(response)
    output_payload = {
        "workspace_id": workspace,
        "result": result.get("result", {}),
        "provenance": result.get("provenance", {}),
        "request_id": result.get("request_id"),
    }
    if export_path:
        path = Path(export_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if export_format.strip().lower() == "csv":
            rows = result.get("result", {}).get("rows", [])
            columns = result.get("result", {}).get("columns", [])
            column_names = [str(col.get("name", "")) for col in columns if isinstance(col, dict)]
            lines = [",".join(column_names)]
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, list):
                        lines.append(",".join(str(item) for item in row))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            path.write_text(json.dumps(output_payload, indent=2, sort_keys=True), encoding="utf-8")
        output_payload["export_path"] = path.as_posix()
        output_payload["export_format"] = export_format.strip().lower()
    typer.echo(json.dumps(output_payload, indent=2, sort_keys=True))


def _parse_json_mapping(raw: str, *, field_name: str) -> dict[str, object]:
    text = raw.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON for {field_name}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not isinstance(parsed, dict):
        typer.echo(f"JSON for {field_name} must be an object.", err=True)
        raise typer.Exit(code=1)
    return {str(key): value for key, value in parsed.items()}


@app.command("policy-simulate")
def policy_simulate(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    actor_type: str = typer.Option("human", "--actor-type"),
    actor_roles: str = typer.Option("data_steward", "--actor-roles"),
    actor_attributes_json: str = typer.Option("{}", "--actor-attributes"),
    resource_attributes_json: str = typer.Option("{}", "--resource-attributes"),
    action: str = typer.Option("query", "--action"),
    gateway_base_url: str = typer.Option(DEFAULT_GATEWAY_BASE_URL, "--gateway-base-url"),
) -> None:
    """Run policy simulation without returning data rows."""
    attributes = _parse_json_mapping(actor_attributes_json, field_name="actor_attributes")
    resource_attrs = _parse_json_mapping(resource_attributes_json, field_name="resource_attributes")
    roles = [item.strip() for item in actor_roles.split(",") if item.strip()]
    payload = {
        "workspace_id": workspace,
        "actor": {
            "actor_type": actor_type.strip().lower() or "human",
            "roles": roles,
            "attributes": attributes,
        },
        "resource_attributes": resource_attrs,
        "action": action.strip() or "query",
    }
    response = _request_json(
        "POST",
        f"{gateway_base_url}/api/v1/gateway/policy/simulate",
        payload,
        auth_token=os.getenv("SCHEMAPILOT_GATEWAY_STEWARD_TOKEN", "local-data-steward-token"),
    )
    typer.echo(json.dumps(_as_dict(response), indent=2, sort_keys=True))


@app.command("policy-audit-report")
def policy_audit_report(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    scenarios_path: str = typer.Option(..., "--scenarios"),
    output: str = typer.Option("runtime/audit/policy_audit_report.json", "--output"),
    gateway_base_url: str = typer.Option(DEFAULT_GATEWAY_BASE_URL, "--gateway-base-url"),
) -> None:
    """Generate a deterministic policy simulation report from scenario file."""
    scenario_file = Path(scenarios_path)
    if not scenario_file.exists():
        typer.echo(f"Scenarios file not found: {scenario_file.as_posix()}", err=True)
        raise typer.Exit(code=1)
    scenarios_raw = json.loads(scenario_file.read_text(encoding="utf-8"))
    if not isinstance(scenarios_raw, list):
        typer.echo("Scenarios file must contain a list.", err=True)
        raise typer.Exit(code=1)
    report_rows: list[dict[str, object]] = []
    for scenario in scenarios_raw:
        if not isinstance(scenario, dict):
            continue
        scenario_id = str(scenario.get("id", new_ulid()))
        actor = scenario.get("actor", {})
        resource_attrs = scenario.get("resource_attributes", {})
        action = str(scenario.get("action", "query"))
        payload = {
            "workspace_id": workspace,
            "actor": actor if isinstance(actor, dict) else {},
            "resource_attributes": resource_attrs if isinstance(resource_attrs, dict) else {},
            "action": action,
        }
        result = _request_json(
            "POST",
            f"{gateway_base_url}/api/v1/gateway/policy/simulate",
            payload,
            auth_token=os.getenv("SCHEMAPILOT_GATEWAY_STEWARD_TOKEN", "local-data-steward-token"),
        )
        parsed = _as_dict(result)
        report_rows.append(
            {
                "id": scenario_id,
                "result": parsed.get("result", "deny"),
                "reason": parsed.get("reason", "unknown"),
                "applied_masks": parsed.get("applied_masks", {}),
                "applied_filters": parsed.get("applied_filters", {}),
            }
        )
    report_payload = {
        "workspace_id": workspace,
        "scenario_count": len(report_rows),
        "scenarios": report_rows,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")
    typer.echo(json.dumps({"output_path": output_path.as_posix(), "scenario_count": len(report_rows)}))


@app.command("analyze")
def analyze(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    database_url: str = typer.Option(DEFAULT_DATABASE_URL, "--database-url"),
) -> None:
    """Analyze denials, review queue state, runs, and outbox backlog for a workspace."""
    report = analyze_workspace(database_url=database_url, workspace_id=workspace)
    typer.echo(json.dumps(report, indent=2, sort_keys=True))


@app.command("diag-bundle")
def diag_bundle(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    output: str = typer.Option("runtime/diag/diagnostics.zip", "--output"),
    database_url: str = typer.Option(DEFAULT_DATABASE_URL, "--database-url"),
    config_path: str | None = typer.Option(None, "--config"),
    max_rows: int = typer.Option(200, "--max-rows"),
) -> None:
    """Create a redacted diagnostics zip bundle for operator support."""
    report = generate_diag_bundle(
        workspace_id=workspace,
        database_url=database_url,
        output_path=output,
        config_path=config_path,
        max_rows=max(max_rows, 1),
    )
    typer.echo(json.dumps(report, indent=2, sort_keys=True))


@app.command("catalog-export")
def catalog_export(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    output: str = typer.Option(..., "--output"),
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
) -> None:
    """Export workspace catalog snapshot to a local file."""
    snapshot = _request_json(
        "GET",
        f"{api_base_url}/api/v1/workspaces/{workspace}/catalog/export",
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    typer.echo(json.dumps({"output_path": output_path.as_posix()}, indent=2))


@app.command("catalog-import")
def catalog_import(
    workspace: str = typer.Option(..., "--workspace", "-w"),
    input_path: str = typer.Option(..., "--input"),
    api_base_url: str = typer.Option(DEFAULT_API_BASE_URL, "--api-base-url"),
) -> None:
    """Import a redacted catalog snapshot file into a workspace."""
    path = Path(input_path)
    if not path.exists():
        typer.echo(f"Catalog snapshot not found: {path.as_posix()}", err=True)
        raise typer.Exit(code=1)
    payload = json.loads(path.read_text(encoding="utf-8"))
    response = _request_json(
        "POST",
        f"{api_base_url}/api/v1/workspaces/{workspace}/catalog/import",
        {"snapshot": payload},
    )
    typer.echo(json.dumps(response, indent=2, sort_keys=True))


@app.command("demo-generate")
def demo_generate(
    output_root: str = typer.Option("runtime/demo/first_hour", "--output-root"),
) -> None:
    """Generate deterministic first-hour demo data files."""
    result = generate_demo_scenario(output_root=output_root)
    typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))


@app.command("kpi-report")
def kpi_report(
    week: str = typer.Option(..., "--week"),
    ttfsa_minutes: float = typer.Option(..., "--ttfsa-minutes"),
    install_success_rate: float = typer.Option(..., "--install-success-rate"),
    security_regressions: int = typer.Option(..., "--security-regressions"),
    deterministic_pass_rate: float = typer.Option(..., "--deterministic-pass-rate"),
    active_contributors: int = typer.Option(..., "--active-contributors"),
    issue_response_hours: float = typer.Option(..., "--issue-response-hours"),
) -> None:
    """Write weekly KPI report to runtime/kpi."""
    _run(
        [
            sys.executable,
            "tools/kpi_tracker.py",
            "--week",
            week,
            "--ttfsa-minutes",
            str(ttfsa_minutes),
            "--install-success-rate",
            str(install_success_rate),
            "--security-regressions",
            str(security_regressions),
            "--deterministic-pass-rate",
            str(deterministic_pass_rate),
            "--active-contributors",
            str(active_contributors),
            "--issue-response-hours",
            str(issue_response_hours),
        ]
    )


@app.command("migrate-up")
def migrate_up(
    alembic_ini: str = typer.Option("alembic.ini", "--alembic-ini"),
) -> None:
    """Apply database migrations to latest revision."""
    _run([sys.executable, "-m", "alembic", "-c", alembic_ini, "upgrade", "head"])


@app.command("migrate-status")
def migrate_status(
    alembic_ini: str = typer.Option("alembic.ini", "--alembic-ini"),
) -> None:
    """Show current database migration revision."""
    _run([sys.executable, "-m", "alembic", "-c", alembic_ini, "current"])


@app.command()
def check() -> None:
    """Run local quality checks."""
    _run([sys.executable, "tools/check_tooling_baseline.py"])
    _run([sys.executable, "tools/smoke_test.py"])
    typer.echo("check: ok")


@app.command("ssot-verify")
def ssot_verify() -> None:
    """Run SSOT verification checks."""
    _run([sys.executable, "tools/ssot_verify.py"])


@templates_app.command("list")
def templates_list() -> None:
    """List available gold template packs."""
    typer.echo(json.dumps({"packs": list_gold_template_packs()}, indent=2, sort_keys=True))


@templates_app.command("apply")
def templates_apply(
    pack: str = typer.Argument(..., help="Template pack id (invoices|crm|support)"),
    workspace: str = typer.Option(..., "--workspace", "-w"),
    output_root: str = typer.Option("runtime/gold_templates", "--output-root"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    """Generate a deterministic gold template bundle for a workspace."""
    try:
        result = generate_gold_template_bundle(
            pack_id=pack,
            workspace_id=workspace,
            output_root=output_root,
            overwrite=overwrite,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


app.add_typer(templates_app, name="templates")
app.add_typer(plugins_app, name="plugins")


@plugins_app.command("scaffold")
def plugins_scaffold(
    name: str = typer.Option(..., "--name", help="Plugin package name"),
    output_root: str = typer.Option("plugins/generated", "--output-root"),
) -> None:
    """Generate a connector plugin scaffold with tests."""
    normalized = name.strip().lower().replace("-", "_")
    if not normalized:
        typer.echo("Plugin name is required.", err=True)
        raise typer.Exit(code=1)
    package_root = Path(output_root) / normalized
    if package_root.exists():
        typer.echo(f"Plugin scaffold already exists: {package_root.as_posix()}", err=True)
        raise typer.Exit(code=1)
    module_dir = package_root / normalized
    tests_dir = package_root / "tests"
    module_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    (module_dir / "__init__.py").write_text(
        f'"""Connector plugin package for {normalized}."""\n',
        encoding="utf-8",
    )
    (module_dir / "connector.py").write_text(
        textwrap.dedent(
            f"""
            \"\"\"Connector plugin scaffold for {normalized}.\"\"\"

            from __future__ import annotations


            def discover(scope: dict[str, object]) -> list[dict[str, object]]:
                \"\"\"Discover source export artifacts and return deterministic rows.\"\"\"
                root_path = str(scope.get("root_path", "")).strip()
                if not root_path:
                    raise ValueError("root_path_required")
                return [
                    {{
                        "path": f"{{root_path}}/sample_export.csv",
                        "dataset_family": "{normalized}_dataset",
                        "size_bytes": 0,
                        "mtime_epoch": 0.0,
                        "content_hash_sample": "",
                    }}
                ]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (tests_dir / "test_connector.py").write_text(
        textwrap.dedent(
            f"""
            from __future__ import annotations

            from {normalized}.connector import discover


            def test_discover_requires_root_path() -> None:
                try:
                    discover({{}})
                except ValueError as exc:
                    assert str(exc) == "root_path_required"
                else:  # pragma: no cover
                    raise AssertionError("expected root_path_required")
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (package_root / "README.md").write_text(
        textwrap.dedent(
            f"""
            # {normalized}

            Connector plugin scaffold generated by `schemapilot plugins scaffold`.

            ## Entry point

            - `schemapilot.connectors`: `{normalized} = {normalized}.connector:discover`
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (package_root / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [build-system]
            requires = ["setuptools>=69", "wheel"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "{normalized}"
            version = "0.1.0"
            requires-python = ">=3.12"
            dependencies = []

            [project.entry-points."schemapilot.connectors"]
            {normalized} = "{normalized}.connector:discover"

            [tool.setuptools]
            include-package-data = true

            [tool.setuptools.packages.find]
            where = ["."]
            include = ["{normalized}*"]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    typer.echo(json.dumps({"package_root": package_root.as_posix(), "name": normalized}, indent=2))


def main() -> None:
    """CLI process entrypoint."""
    app()


if __name__ == "__main__":
    main()
