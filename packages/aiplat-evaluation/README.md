# aiplat-evaluation

Evaluation Service **D1 Thin (D1c/cohost)** · **D2 ops pack** · A3 Accepted（有条件）.

- Healthz: `GET /api/core/eval/healthz` (`product_id=evaluation`)
- Protocol: `eval.protocol.v0`
- Install/upgrade/rollback/smoke: `scripts/d1_*.sh`
- D2 pack: [`docs/D2_COHOST.md`](./docs/D2_COHOST.md) · `scripts/d2_admin_check.sh` · `scripts/d2_local_closeout.sh`
- Docs: [`docs/INSTALL.md`](./docs/INSTALL.md) · [`SECURITY.md`](./docs/SECURITY.md) · [`PERF_BASELINE.md`](./docs/PERF_BASELINE.md)

`process_split_authorized` stays **false** until live checklist ✅.

Charter: `reports/five-products/modules/evaluation/MODULE.md`
