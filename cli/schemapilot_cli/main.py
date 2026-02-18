"""SchemaPilot CLI entrypoint."""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib import error as urlerror
from urllib.parse import urlparse

import typer

app = typer.Typer(help="SchemaPilot CLI")
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_CP_AUTH_TOKEN = os.getenv("SCHEMAPILOT_CP_TOKEN", "local-platform-admin-token")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    typer.echo("$ " + " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def _request_json(
    method: str, url: str, payload: Mapping[str, object] | None = None
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
    if DEFAULT_CP_AUTH_TOKEN.strip():
        headers["Authorization"] = f"Bearer {DEFAULT_CP_AUTH_TOKEN.strip()}"
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
def doctor() -> None:
    """Run environment preflight checks."""
    _run([sys.executable, "tools/ssot_verify.py"])
    _run([sys.executable, "tools/verify_manifest.py"])
    typer.echo("doctor: ok")


@app.command()
def init(profile: str = "team") -> None:
    """Generate local config skeleton."""
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


def main() -> None:
    """CLI process entrypoint."""
    app()


if __name__ == "__main__":
    main()
