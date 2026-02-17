# ENTERPRISE_RELEASE_CHECKLIST.md

## Purpose
Use this checklist to validate SchemaPilot in an enterprise-like staging environment before release.

Release decision rule:
- `GO` only if all `P0` and `P1` checks pass with evidence.
- `NO-GO` if any `P0` fails.

## Environment Baseline
- Dedicated staging environment (no shared dev resources).
- `enterprise` profile deployment path validated.
- Separate metadata DB, object store, and policy service (OPA path).
- External exposure only through approved ingress/reverse proxy + auth.

## Required Preflight
Run and archive output:
```bash
python tools/cleanroom_install_check.py
python -m cli.schemapilot_cli.main doctor
python -m cli.schemapilot_cli.main check
python tools/ssot_verify.py
python tools/verify_manifest.py
```

Pass criteria:
- All commands exit `0`.
- Clean-room check reports `PASS clean-room install check`.
- `PASS CHK-TOOLING-BASELINE`, `PASS CHK-SMOKE`, `PASS`.

Evidence artifacts:
- `evidence/t0046/final_schemapilot_check.txt`
- CI run URL / pipeline logs
- `runtime/cleanroom/summary.txt`

## Enterprise Test Matrix

| ID | Priority | Scenario | How To Execute | Pass Criteria | Evidence |
|---|---|---|---|---|---|
| ER-001 | P0 | Secure startup defaults | Start with non-local bind and missing auth | Service fails to start clearly | service logs + config snippet |
| ER-002 | P0 | Gateway non-bypass | Attempt direct engine/index access from client network | Direct access denied; gateway path only | e2e logs + network policy output |
| ER-003 | P0 | Deny-by-default AI | Query/retrieve as AI actor not allowlisted | `403 POLICY_DENIED` | gateway response + audit rows |
| ER-004 | P0 | OPA fail-closed | Enable OPA mode, stop OPA, retry request | Request denied (`opa_unavailable`/policy deny) | gateway logs + response |
| ER-005 | P0 | Row/column governance | Query sensitive fields as constrained role | Masking/filters applied correctly | query output + access_decisions |
| ER-006 | P0 | Audit completeness | Run create/review/build/query/retrieve flows | Audit rows exist with correlation IDs | DB query dump + logs |
| ER-007 | P0 | Gold fail-closed publish | Force contract failure then publish | publish blocked; last good remains | publish response + pointer file diff |
| ER-008 | P0 | Deletion legal hold block | Submit deletion with legal hold active | status `blocked`, reason `legal_hold_active` | workflow response + audit event |
| ER-009 | P0 | Deletion approved execution | Submit approved deletion | evidence report written, deterministic fields present | report JSON + audit event |
| ER-010 | P1 | Document retrieval policy | Retrieve with allowed/denied dataset scopes | only allowed dataset results returned with citations | retrieve responses |
| ER-011 | P1 | Prompt-injection resilience | Ingest malicious doc text and retrieve | content treated as data only; no control action triggered | retrieval logs + output |
| ER-012 | P1 | Secrets hygiene | Run scanner + inspect logs | no leaked secrets; redaction works | scanner output + sampled logs |
| ER-013 | P1 | Secrets rotation drill | `python tools/secrets_rotation_drill.py` | drill passes and report generated | `runtime/secrets_rotation_drill/report.json` |
| ER-014 | P0 | Backup/restore drill | `python tools/backup_restore_drill.py` | `PASS CHK-BACKUP-RESTORE`; restored state valid | `runtime/backup_restore_drill/report.json` |
| ER-015 | P1 | Upgrade drill Starter->Team | run upgrade drill tests/harness | IDs stable, no re-ingest required | upgrade test logs |
| ER-016 | P1 | MessyBench regression | `python tools/messybench_harness.py` | pass with stable machine-readable output | `runtime/messybench/results.json` |
| ER-017 | P1 | Perf regression gate | `python tools/perf_harness.py` | `PASS CHK-PERF-HARNESS` | `runtime/perf/results.json` |
| ER-018 | P1 | Observability completeness | hit `/api/v1/metrics` on API + gateway | required metrics exposed | metric scrape output + dashboard screenshot |
| ER-019 | P1 | Review queue operability | create blocking/non-blocking review tasks | backlog visible; gating behavior correct | API/UI screenshots + logs |
| ER-020 | P2 | Soak/stability run | 4-24h repeated ingest/query/retrieve workload | no crash loops, controlled errors, stable latency envelope | soak report |

## Execution Order
1) Preflight and deployment checks (`ER-001` to `ER-004`)  
2) Governance and audit checks (`ER-005` to `ER-011`)  
3) Ops drills (`ER-012` to `ER-015`)  
4) Regression/perf/observability (`ER-016` to `ER-020`)

## Sign-Off
- Security lead: `APPROVE / BLOCK`
- Data governance lead: `APPROVE / BLOCK`
- Platform/ops lead: `APPROVE / BLOCK`
- Product owner: `APPROVE / BLOCK`

Release decision:
- `GO` only if all P0 checks pass and all sign-offs are `APPROVE`.

## Automated Gate Command
Run a full gate and generate a JSON report:
```bash
python tools/release_gate.py --output runtime/release_gate/report.json
```

Pass criteria:
- report status is `go`.
- each step status is `pass`.

## Recommended Evidence Bundle
- Command transcript and CI links
- API/gateway responses for policy checks
- Audit DB extracts (sanitized)
- Backup/restore + secrets rotation reports
- MessyBench + perf JSON outputs
- Dashboard screenshot and metric scrape snippets
