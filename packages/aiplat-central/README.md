# aiplat-central

Central host packaging for capability `aiplat` (Thin).

- Contracts: `contracts/schemas/healthz.schema.json` (`product_id=aiplat`)
- Install/upgrade/rollback/backup/smoke: `scripts/d1_*.sh`
- A2 version / D2 compat / D2+ security: `scripts/a2_version_check.sh` · `d2_compat_check.sh` · `d2_security_check.sh`
- D2 Thin local closeout: `scripts/d2_local_closeout.sh` · [`docs/D2_THIN.md`](./docs/D2_THIN.md)
- PG/HA: `docs/pg_ha/` · cutover stays unauthorized until checklist all green + production_signed live

Module charter: `reports/five-products/modules/aiplat/MODULE.md`
