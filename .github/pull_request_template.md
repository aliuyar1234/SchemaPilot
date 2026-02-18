## Summary

Describe what changed and why.

## Linked issue(s)

- Issue:

## Risk and impact

- Critical flow impacted: (yes/no)
- Security impact:
- Backward compatibility impact:

## Verification

Run and paste results:

```text
python tools/check_tooling_baseline.py
python tools/verify_manifest.py
python -m pytest -q
```

If applicable, include focused test commands for changed modules.

## Checklist

- [ ] Tests added/updated for changed behavior
- [ ] `MANIFEST.sha256` regenerated (if tracked files changed)

## Notes for reviewers

List tradeoffs, intentional follow-ups, or non-blocking questions.
