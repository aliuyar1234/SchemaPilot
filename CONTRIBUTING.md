# Contributing to SchemaPilot

SchemaPilot is built around a fail-closed, evidence-first governance model. Thanks for helping improve it.

## Before you start

1. Read `README.md` and `ARCHITECTURE.md`.
2. Open or reference an issue describing the change.
3. Keep architecture boundaries intact (`tools/check_boundary_fitness.py`).

## Local setup

```powershell
python -m pip install -e ".[dev]"
```

## Required checks before opening a PR

```powershell
python tools/check_tooling_baseline.py
python tools/verify_manifest.py
python -m pytest -q
```

If you changed tracked files, regenerate the manifest first:

```powershell
python tools/generate_manifest.py
python tools/verify_manifest.py
```

## Contribution rules

1. Keep changes small and focused.
2. Add tests for new behavior, especially negative-path and fail-closed behavior.
3. Do not weaken security defaults or bypass gateway enforcement.

## Connectors and plugin contributions

1. Prefer read-only discovery semantics.
2. Fail closed on ambiguous auth, partial listings, or unsupported capabilities.
3. Include deterministic behavior notes and tests.

## Pull request expectations

1. Explain the problem and approach.
2. List verification commands and results.
3. Call out any risks, follow-ups, or intentional deferrals.

## Security reporting

Please do not publish security issues in public issues.

1. Use GitHub private vulnerability reporting (preferred).
2. If unavailable, open a minimal issue asking maintainers for a private channel without disclosing exploit details.
