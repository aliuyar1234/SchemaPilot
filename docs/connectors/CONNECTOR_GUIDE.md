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
- Pass connector conformance harness before release.

## Connector tiers

- `recommended`: hard-gated in conformance/release checks.
- `community`: validated, but not release-blocking by default.

Current `recommended` first-party set:

- `jira`
- `zendesk_export`
- `sharepoint`
- `google_drive`
- `smb`
- `sftp`

## Signing and verification

- Add plugin names to allowlist: `SCHEMAPILOT_PLUGINS_ALLOWED=acme_connector`
- Sign registry metadata: `schemapilot plugins sign --registry plugins/registry.json`
- Verify registry metadata: `schemapilot plugins verify --registry plugins/registry.json`
- Enterprise profile enforces signed plugin metadata and blocks unsigned/tampered entries.
- Plugin registry entries support `tier: recommended|community` metadata.

## Reference examples

- `plugins/examples/hubspot_export_connector.py`
- `plugins/examples/zendesk_export_connector.py`
