# spec/08_OBSERVABILITY.md

## Observability Strategy

Observability MUST provide:
- proof of correctness (not just “logs exist”),
- actionable diagnostics for operators,
- security audit trails for governance and enforcement.

This requires:
- structured logs with correlation IDs,
- metrics for ingestion/build health and policy enforcement,
- optional traces for cross-service latency,
- append-only audit logging with immutable records.

## Logging Standard

Format:
- Structured JSON logs for services and workers.

Required fields (minimum):
- `level`
- `msg`
- `service` (control_plane, worker, gateway, ui)
- `correlation_id` (ULID; run/build/query scoped)
- `workspace_id` (when applicable)
- `actor_id` (gateway/audit events)
- `event_type` (when applicable)

Redaction rules:
- MUST redact secrets and sensitive values.
- MUST NOT log raw row samples containing PII unless explicitly configured in a secure dev-only mode.
evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secrets Handling

## Metrics

The following metrics MUST exist (names are normative; labels may vary):

1) `schemapilot_ingest_lag_seconds` (labels: workspace_id, source_id)
2) `schemapilot_parse_failures_total` (labels: workspace_id, source_type, dataset_id)
3) `schemapilot_profiling_coverage_ratio` (labels: workspace_id)
4) `schemapilot_drift_events_total` (labels: workspace_id, severity)
5) `schemapilot_silver_quarantine_rows_total` (labels: workspace_id, entity_name)
6) `schemapilot_contract_failures_total` (labels: workspace_id, layer)
7) `schemapilot_review_queue_backlog_total` (labels: workspace_id, priority)
8) `schemapilot_query_latency_ms` (histogram; labels: workspace_id, engine, result)
9) `schemapilot_policy_denials_total` (labels: workspace_id, reason)
10) `schemapilot_cost_bytes_scanned_total` (labels: workspace_id, engine)

## Tracing

- Use OpenTelemetry where feasible.
- Trace context must propagate:
  - UI → API → orchestrator → worker runs
  - gateway → policy engine → engine/index

Tracing is optional in Starter but required in Enterprise profiles.

## Audit Logging Signals

Audit logs must support:
- who did what, when, and why
- policy decisions and applied masking/filtering
- linkage to runs/builds and their inputs/outputs

Audit invariants:
- append-only; immutable
- correlation_id present
evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.audit_events (append-only)

## Dashboards and Alerts

Dashboards MUST include:
- ingestion health (lag, failure rates)
- drift and schema change activity
- review queue backlog (risk-focused)
- contract failures and gold publish status
- policy denial rates and anomalies

Alerting principles (avoid fixed thresholds when scale unknown):
- Alert on deviation from established baseline and on sustained errors.
- Require explicit decisions when changing alert thresholds.
evidence: spec/11_QUALITY_GATES.md :: G-PERF-0001 Performance Harness and No Regression
