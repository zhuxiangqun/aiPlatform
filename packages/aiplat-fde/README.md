# aiplat-fde

FDE **Field D1** packaging · ADR **Accepted** (`ADR-FDE-FIELD-DEPLOY`) · **Field D2 ops pack**.

- Install/upgrade/backup/rollback/smoke: `scripts/d1_*.sh`
- D2 pack: [`docs/D2_FIELD.md`](./docs/D2_FIELD.md) · `scripts/d2_admin_check.sh` · `scripts/d2_local_closeout.sh`
- Docs: [`docs/INSTALL.md`](./docs/INSTALL.md) · N-1 · data residency
- Healthz: `GET /api/core/fde/healthz` (`production_field=true`)
- Signoff: `POST /api/platform/apps/fde/acceptance/signoff`
