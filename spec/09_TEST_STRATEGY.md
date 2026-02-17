# spec/09_TEST_STRATEGY.md

## Test Pyramid

SchemaPilot MUST implement tests across these levels:

### Unit tests
- Pure functions: scoring, confidence calculations, parsing helpers, policy evaluation adapters.
- Deterministic: time and randomness are controlled.

### Integration tests
- Postgres schema/migrations
- Object store layout and manifest writing
- Query Gateway against DuckDB (Starter) and Trino (Team) in containerized test setup

### End-to-end tests
- Wizard journey: connect → catalog → review → silver/gold → first query
- Review Queue workflow: create tasks → approve/reject → gating behavior
- Non-bypass: attempts to query engines directly are blocked (network/config enforcement)

### Security tests
- Deny-by-default tests for AI tool identity
- Secrets redaction tests
- Policy decision logging and provenance completeness tests

### Performance tests (harness-first)
- Provide repeatable harness for:
  - profiling budgets (bounded)
  - decision engine runtime on representative catalog
  - gateway query latency baseline
- Enforce “no regression without decision + mitigation + evidence”
evidence: spec/11_QUALITY_GATES.md :: G-PERF-0001 Performance Harness and No Regression

## Determinism and Reproducibility

Rules:
- Avoid non-deterministic ordering in outputs (sort by stable keys).
- Control random seeds in ER sampling.
- Snapshot and version all transforms.
- Gold outputs must be reproducible from:
  - bronze snapshot refs,
  - transform versions,
  - configuration.

Enforcement:
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0002 Deterministic Builds

## Negative Path Requirements

The system MUST be tested for fail-closed behavior:

- If contracts fail: gold is not published; last known good stays active.
- If confidence low on high-risk proposals: review required; no auto-apply.
- If gateway policy denies: query fails with stable error code; audit event emitted.
- If extraction fails: raw stored; indexing deferred; review task created.
evidence: CONSTITUTION.md :: SB-0004 Untested error paths

## MessyBench (OSS benchmark plan)

MessyBench is a bundled benchmark suite for “messy reality”:
- inconsistent headers, multilingual values, locale dates, encoding issues
- duplicates and missing IDs
- partial exports and schema drift
- PDFs/emails with mixed extraction quality and ground-truth references

MessyBench deliverables in the implementation repo:
- synthetic generator producing datasets and ground-truth expectations
- golden expected outputs:
  - canonical entity schemas
  - ER match labels (precision/recall)
  - expected decision engine template rankings
  - expected gold metric outputs for a fixed Q/A set
- CI harness that runs on every PR and produces machine-readable results

## CI Gates Mapping

CI must run checks and tests mapped to quality gates:
- evidence: spec/11_QUALITY_GATES.md :: Gate Index
