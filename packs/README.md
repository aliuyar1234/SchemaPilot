# SchemaPilot Pack Registry

This folder contains explicit, allowlisted pack artifacts:

- Policy packs: `packs/policy/*.json`
- Semantic starter packs: `packs/semantic/*.json`
- Gold template metadata packs: `packs/templates/*.json`
- Connector examples: referenced in `packs/registry.json`
- Compatibility matrix: `packs/compatibility_matrix.json`

Validate registry integrity with:

```bash
python tools/pack_lint.py
```

Sign or refresh pack signatures:

```bash
python tools/pack_lint.py --write-signatures
```

Migrate packs to current schema versions declared by the compatibility matrix:

```bash
python tools/pack_migrate.py --write
```

Install/apply behavior remains explicit and fail-closed; packs are not auto-downloaded.
