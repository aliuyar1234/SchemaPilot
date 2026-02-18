# Plugin SDK (Connector + Check)

SchemaPilot plugins extend the system without bypassing core security boundaries.

## Scope and Safety

- Connector plugins: discovery + bronze ingest only.
- Check plugins: quality/security checks producing machine-readable results.
- Plugins must not bypass gateway policy enforcement for query/retrieval.

## Connector plugin example

See `plugins/examples/connector_plugin_example.py`.

Expected shape:

- `plugin_id() -> str`
- `discover(scope: dict[str, object]) -> list[dict[str, object]]`

## Check plugin example

See `plugins/examples/check_plugin_example.py`.

Expected shape:

- `check_id() -> str`
- `run_check() -> dict[str, object]`

Output should include:

- `status`: `pass` or `fail`
- `details`: machine-readable context

## Packaging notes

- Keep dependencies minimal.
- Expose plugin entrypoints through your package metadata.
- Document capability restrictions in plugin README.

## Entry point registration

Use Python package entry points so SchemaPilot can discover plugins without ad-hoc imports.

Example `pyproject.toml`:

```toml
[project]
name = "schemapilot-acme-plugins"
version = "0.1.0"

[project.entry-points."schemapilot.connectors"]
acme_export_connector = "acme_plugins.connector:discover"

[project.entry-points."schemapilot.checks"]
acme_schema_check = "acme_plugins.checks:run_check"
```

Recommended package layout:

- `acme_plugins/connector.py` with `plugin_id()` and `discover(...)`
- `acme_plugins/checks.py` with `check_id()` and `run_check()`
- `README.md` with capabilities, required scopes, and fail-closed behavior

## Publish and validate

1) Build and install plugin package in the same environment as SchemaPilot.
2) Run `schemapilot check` to verify plugin checks remain deterministic and fail-closed.
3) Confirm plugin output is machine-readable and does not bypass gateway enforcement.
