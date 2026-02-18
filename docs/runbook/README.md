# Operator Runbook Index

Canonical operator runbook content lives in `spec/12_RUNBOOK.md`.

Use this file as a stable docs entrypoint and quick map:

- Local demo onboarding path: `spec/12_RUNBOOK.md` (`Demo Path: Local Folders to First Governed Query`)
- Safe exposure and OIDC configuration: `spec/12_RUNBOOK.md` (`Safe exposure (non-local)`)
- JWT/JWKS auth mode and trusted-proxy mode: `spec/12_RUNBOOK.md` (`OIDC-first enterprise integration`)
- Strict ingest defaults and no-partial-ingest behavior: `spec/12_RUNBOOK.md` (`Strict ingest completeness defaults`)
- Retention/deletion safety controls: `spec/12_RUNBOOK.md` (`Retention/deletion safety defaults`)
- Plugin allowlist + isolation controls: `spec/12_RUNBOOK.md` (`Plugin security defaults`)
- OpenAPI/e2e regression checks: `spec/12_RUNBOOK.md` (`Contract and regression gates`)
- Weekly KPI workflow and artifacts: `spec/12_RUNBOOK.md` (`Weekly KPI report command`)
- Troubleshooting matrix: `spec/12_RUNBOOK.md` (`Troubleshooting`)

Weekly KPI example:

```bash
python tools/kpi_tracker.py \
  --week 2026-W08 \
  --ttfsa-minutes 24 \
  --install-success-rate 0.92 \
  --security-regressions 0 \
  --deterministic-pass-rate 1.0 \
  --active-contributors 5 \
  --issue-response-hours 12
```

Expected outputs:

- `runtime/kpi/weekly/<week>.json`
- `runtime/kpi/latest.json`
