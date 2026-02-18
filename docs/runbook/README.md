# Operator Runbook Index

Canonical operator runbook content lives in `spec/12_RUNBOOK.md`.

Use this file as a stable docs entrypoint and quick map:

- Local demo onboarding path: `spec/12_RUNBOOK.md` (`Demo Path: Local Folders to First Governed Query`)
- Safe exposure and OIDC configuration: `spec/12_RUNBOOK.md` (`Safe exposure (non-local)`)
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
