# Failure Codes Runbook

This document is the canonical operator mapping for run-step `failure_code` values.
The taxonomy version is `v1`.

## FC-0000_UNKNOWN

- Category: `unknown`
- Meaning: The failure did not match a known class. Treat as unclassified and inspect evidence.
- Next actions:
  - Review run-step `details.error` and `evidence_bundle_uri`.
  - Reproduce with `schemapilot doctor` and `schemapilot diag-bundle`.
  - Escalate with diagnostics if repeated.

## FC-0001_SECRETS

- Category: `secrets`
- Meaning: Secret loading, rotation, or key-access path failed.
- Next actions:
  - Validate secrets backend settings and key references.
  - Verify secret material exists and is readable by service identity.
  - Re-run after rotation/credential repair.

## FC-0002_AUTHZ

- Category: `authz`
- Meaning: Authorization/policy checks denied the operation.
- Next actions:
  - Inspect policy denies in `schemapilot analyze --workspace <workspace_id>`.
  - Confirm actor role/attributes and dataset entitlements.
  - Resolve review tasks or policy pack changes before retry.

## FC-0003_STRICT_COMPLETENESS

- Category: `strict_completeness`
- Meaning: Strict ingest completeness gate failed and blocked run completion.
- Next actions:
  - Open referenced evidence bundle and identify failed source items.
  - Fix source availability/scope and rerun discovery.
  - Resolve generated blocking review task after remediation.

## FC-0004_DRIFT

- Category: `drift`
- Meaning: Schema or semantic drift check failed.
- Next actions:
  - Review drift evidence and proposed changes.
  - Approve/adjust impacted policy or semantic artifacts.
  - Re-run after corrective action.

## FC-0005_SCHEMA_MISMATCH

- Category: `schema_mismatch`
- Meaning: Contracts, expected schema, or run-type contract did not match runtime input.
- Next actions:
  - Compare expected vs actual contract/schema payload.
  - Update manifest/contract inputs through approved workflow.
  - Retry once schema compatibility is restored.

## FC-0006_ENGINE_UNAVAILABLE

- Category: `engine_unavailable`
- Meaning: Query/target engine dependency was unavailable or unreachable.
- Next actions:
  - Check engine service health and connectivity.
  - Confirm engine profile configuration and credentials.
  - Re-run when service is healthy.

## FC-0007_TIMEOUT

- Category: `timeout`
- Meaning: Worker step exceeded configured timeout/deadline.
- Next actions:
  - Inspect run-step timing and workload size.
  - Tune timeout/batch limits conservatively if justified.
  - Re-run after reducing input scope or scaling resources.

## FC-0008_SANDBOX_VIOLATION

- Category: `sandbox_violation`
- Meaning: Plugin/connector execution violated sandbox or allowlist constraints.
- Next actions:
  - Check plugin allowlist and signing/verification posture.
  - Verify connector capability policy (network/file permissions).
  - Keep plugin disabled until policy-compliant.
