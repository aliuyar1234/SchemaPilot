---
name: Bug report
about: Report a reproducible problem in SchemaPilot
title: "[Bug] "
labels: ["bug"]
assignees: []
---

## Summary

Describe the observed behavior and expected behavior.

## Reproduction steps

1. 
2. 
3. 

## Environment

- OS:
- Python version:
- Install mode: (local / docker compose)
- Profile: (starter / team / enterprise)
- Commit SHA:

## Evidence

- Request IDs / correlation IDs:
- Relevant logs (redacted):
- API response body/status:
- Minimal sample input (if applicable):

## Security/governance impact

- [ ] No security impact
- [ ] Potential policy bypass
- [ ] Potential data leakage
- [ ] Determinism/reproducibility regression

## Checks run

Paste outputs for:

```text
python tools/check_tooling_baseline.py
python tools/verify_manifest.py
python -m pytest -q
```
