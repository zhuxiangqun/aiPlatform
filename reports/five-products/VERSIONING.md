# A2 Versioning（五能力）

> Slice: **A2 versioning only** — independent semver per deploy package.  
> Does **not** Accept Field / PG-HA ADRs. Does **not** claim E4 / full process split.

## Rules

1. **SSOT**: [`versions.yaml`](./versions.yaml) lists each capability’s expected `version`.
2. `packages/*/package.json` `version` **must equal** SSOT.
3. `reports/five-products/modules/*/module.yaml` `version` **must equal** SSOT.
4. Compat matrix `min_version` must be **≤** package version (semver-ish).
5. Bump: patch for contract/smoke fixes; minor for D1/D2 packaging features; major only with ADR / breaking contract.

## Check

```bash
bash packages/aiplat-central/scripts/a2_version_check.sh
```

## Current line

All five Thin/PREP packages at **0.1.0** (2026-10-30).
