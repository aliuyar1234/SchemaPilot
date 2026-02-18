# Upgrade Playbook

This playbook covers conservative upgrades from Starter to Team/Enterprise profiles.

## Preconditions

1. Backup metadata and artifacts:
   - `python tools/backup.py --storage-root runtime/storage --db runtime/schemapilot.db --output runtime/backups/latest`
2. Verify current state:
   - `python -m cli.schemapilot_cli.main doctor`
   - `python tools/verify_manifest.py`

## Starter -> Team

1. Apply migration status check:
   - `python -m cli.schemapilot_cli.main migrate-status`
2. Apply migrations if needed:
   - `python -m cli.schemapilot_cli.main migrate-up`
3. Run upgrade helper:
   - `python tools/upgrade_starter_to_team.py --storage-root runtime/storage --workspace-id <workspace_id>`
4. Start team profile:
   - `docker compose --profile team up -d`
5. Validate no-bypass and gateway health:
   - `python tools/check_no_bypass_ports.py`
   - `curl -s http://127.0.0.1:8001/api/v1/health`

## Team -> Enterprise

1. Configure enterprise auth/env values (OIDC/JWT as required).
2. Start enterprise profile:
   - `docker compose --profile enterprise up -d`
3. Run release gate subset:
   - `python tools/release_gate.py --output runtime/release_gate/report.json`

## Rollback

1. Stop services and restore backup:
   - `python tools/restore.py --input runtime/backups/latest`
2. Restart previous profile.
3. Verify with `doctor` and a gateway query smoke test.
