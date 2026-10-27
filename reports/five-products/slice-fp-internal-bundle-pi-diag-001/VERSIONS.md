# VERSIONS

Bundle 目录不入库。再生与验收请走 live E2E（禁止合成 smoke_ok）：

```bash
bash scripts/slice_e2e.sh --scenario lock-service
bash scripts/slice_e2e.sh --scenario lock-service --inject disconnect
```

`five_products_slice_smoke.py` 仅为兼容包装，已委托 `slice_e2e.sh`。证据与 RUNLOG 入库。

```json
{
  "scene_id": "fp-internal-bundle-pi-diag-001",
  "bundle_version": "20261023-840e3fbd7cf1",
  "report_id": "rep-2551f299acf5",
  "run_id": "pi-live-20261023T155206Z",
  "pi_live_ok": true,
  "export_mjs_fix": true,
  "fault_injection_4of4": true,
  "updated_at": "2026-10-23T15:52:06.253326+00:00"
}
```
