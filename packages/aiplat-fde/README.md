# aiplat-fde

FDE **Field D1** packaging · ADR **Accepted** (`ADR-FDE-FIELD-DEPLOY`).

- Install/backup/rollback/smoke: `scripts/d1_*.sh`
- Docs: [`docs/INSTALL.md`](./docs/INSTALL.md) · N-1 · data residency
- Healthz: `GET /api/core/fde/healthz` (`production_field=true`)
- Signoff: `POST /api/platform/apps/fde/acceptance/signoff`
