# Operator Runbook

This runbook captures the core operator workflows for local/team deployments.

## Daily operations

- Run a preflight check before changes: `schemapilot doctor`
- Inspect governance and run health: `schemapilot analyze --workspace <workspace_id>`
- Generate a redacted support bundle for incidents:
  - `schemapilot diag-bundle --workspace <workspace_id>`

## Onboarding path

- Follow the first-hour guide: `docs/quickstart/FIRST_HOUR.md`
- Follow the target database builder flow: `docs/quickstart/DB_BUILDER.md`
- Run interactive onboarding: `schemapilot init-interactive`
- Validate with a governed query:
  - `schemapilot query --workspace <workspace_id> --sql "select 1 as one" --dataset-id <dataset_id>`

## Target DB lifecycle

- Create/list/get target profiles:
  - `schemapilot target-db create ...`
  - `schemapilot target-db list --workspace <workspace_id>`
  - `schemapilot target-db get --workspace <workspace_id> --target-db <target_db_id>`
- Execute lifecycle:
  - `validate`, `provision-plan/apply`, `migrate-plan/apply`, `load-plan/apply`
- Run deterministic sync and inspect state:
  - `schemapilot target-db sync-run ... --strict --wait`
  - `schemapilot target-db sync-status ...`

## Security and governance checks

- Security model reference: `docs/security/SECURITY_MODEL.md`
- Connector/plugin rules: `docs/connectors/CONNECTOR_GUIDE.md`
- Full baseline checks:
  - `python tools/check_tooling_baseline.py`

## Release and maintenance

- Release gate: `python tools/release_gate.py --output runtime/release_gate/report.json`
- Backup/restore drill: `python tools/backup_restore_drill.py`
- Rotation drill: `python tools/secrets_rotation_drill.py`

## Troubleshooting quick list

- If auth fails: verify token/oidc config and bind settings.
- If queries are denied: inspect policy, workspace, and dataset entitlements.
- If publish is blocked: inspect review queue, contracts, and drift tasks.
- If ingest fails: review strict completeness evidence and connector logs.
