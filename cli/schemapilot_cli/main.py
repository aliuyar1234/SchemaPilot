"""SchemaPilot CLI entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(help="SchemaPilot CLI")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    typer.echo("$ " + " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


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
def connect(source: str, root: str | None = None) -> None:
    """Register source intent (bootstrap placeholder)."""
    typer.echo(f"connect: source={source} root={root}")


@app.command()
def run(workspace: str = "default", type: str = "discover") -> None:  # noqa: A002
    """Start a run (bootstrap placeholder)."""
    typer.echo(f"run: workspace={workspace} type={type}")


@app.command()
def status(workspace: str = "default") -> None:
    """Show run/task status (bootstrap placeholder)."""
    typer.echo(f"status: workspace={workspace}")


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
