# Connector Guide (Plugin-first)

SchemaPilot supports connector plugins with explicit allowlists and isolated execution.

## Scaffold a connector

```bash
schemapilot plugins scaffold --name acme_connector --output-root plugins/generated
```

## Register entry point

Generated scaffold adds:

- `project.entry-points."schemapilot.connectors"`
- `connector.py` with deterministic `discover(scope)` contract

## Strict mode expectations

- Return deterministic discovery rows.
- Include stable `path` and `dataset_family` values.
- Fail fast on missing mandatory scope fields.
- Do not emit partial results silently in strict ingest mode.

## Reference examples

- `plugins/examples/hubspot_export_connector.py`
- `plugins/examples/zendesk_export_connector.py`
