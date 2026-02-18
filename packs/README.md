# SchemaPilot Pack Registry

This folder contains explicit, allowlisted pack artifacts:

- Policy packs: `packs/policy/*.json`
- Semantic starter packs: `packs/semantic/*.json`
- Connector examples: referenced in `packs/registry.json`

Validate registry integrity with:

```bash
python tools/pack_lint.py
```

Install/apply behavior remains explicit and fail-closed; packs are not auto-downloaded.
