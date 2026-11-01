# aiplat-diagnosis

Diagnosis Service **D1 Thin (D1c/cohost)** · **D2 ops pack** · ADR draft.

- Healthz: `GET /api/platform/apps/diagnosis/healthz` (`product_id=diagnosis`)
- Report schema: `diagnosis.report.v0|v1` · `accuracy_claim=false` · 不自动修复
- Install/upgrade/rollback/smoke: `scripts/d1_*.sh`
- D2 pack: [`docs/D2_COHOST.md`](./docs/D2_COHOST.md) · `scripts/d2_admin_check.sh` · `scripts/d2_local_closeout.sh`
- Docs: [`docs/INSTALL.md`](./docs/INSTALL.md) · [`SECURITY.md`](./docs/SECURITY.md) · [`PERF_BASELINE.md`](./docs/PERF_BASELINE.md)

`process_split_authorized` stays **false** until live checklist ✅ + ADR Accept.

Charter: `reports/five-products/modules/diagnosis/MODULE.md`
