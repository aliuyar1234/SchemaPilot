# Operator Runbook

This runbook captures the core operator workflows for local/team deployments.

## Daily operations

- Run a preflight check before changes: `schemapilot doctor`
- Inspect governance and run health: `schemapilot analyze --workspace <workspace_id>`
- Export SLO/SLA health snapshot: `schemapilot slo export --workspace <workspace_id> --format json`
- Redacted export for non-admin sharing: `schemapilot slo export --workspace <workspace_id> --role analyst --redacted --format json`
- Generate a redacted support bundle for incidents:
  - `schemapilot diag-bundle --workspace <workspace_id>`
  - validate bundle redaction before sharing: `python tools/diag_bundle_verify.py <bundle.zip>`

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
- Verify pack signatures before rollout: `python tools/pack_verify.py`
- Prepare deterministic pack schema migrations: `python tools/pack_migrate.py --registry packs/registry.json --matrix packs/compatibility_matrix.json --write`
- Verify plugin signatures before rollout: `python tools/plugin_verify.py`
- Export and verify signed promotion bundle before prod import:
  - `schemapilot promotion-export --workspace <workspace_id> --output runtime/promotion/bundle.json`
  - `python tools/promotion_bundle.py verify --input runtime/promotion/bundle.json`
- Import promotion bundle with policy gates:
  - `schemapilot promotion-import --workspace <prod_workspace_id> --bundle-path runtime/promotion/bundle.json --before-policy-report <before.json> --after-policy-report <after.json>`
- Export governance-only auditor bundle (signed optional):
  - `schemapilot auditor-export --database-url <db_url> --output runtime/auditor/export.json --signing-key <optional_key>`
- Full baseline checks:
  - `python tools/check_tooling_baseline.py`

## Release and maintenance

- Release gate: `python tools/release_gate.py --output runtime/release_gate/report.json`
- AI regression gate only: `python tools/ai_eval_harness.py --regression --output runtime/ai_eval/results_regression.json`
- Backup/restore drill: `python tools/backup_restore_drill.py`
- Rotation drill: `python tools/rotation_drill.py`
- Break-glass drill: `python tools/breakglass_drill.py`

## Troubleshooting quick list

- If auth fails: verify token/oidc config and bind settings.
- If queries are denied: inspect policy, workspace, and dataset entitlements.
- If publish is blocked: inspect review queue, contracts, and drift tasks.
- If ingest fails: review strict completeness evidence and connector logs.
- If a run step fails: map `failure_code` to remediation in `docs/runbook/FAILURE_CODES.md`.
