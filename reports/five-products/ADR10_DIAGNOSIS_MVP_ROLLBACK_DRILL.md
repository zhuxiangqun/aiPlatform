# ADR-10 诊断 MVP — Rollback（Phase A–C）

| Field | Value |
|-------|-------|
| Scene | `fp-customer-lock-service-bundle-pi-diag-001` |
| Date | 2026-10-24（A–B）· **2026-10-26 Phase C 复跑** |
| Result | **PASS** — Phase C 宿主双端×2 + 拒切生产默认；compose 本机无 daemon → SKIP（与 A–B 交付文件仍在） |
| Residual | 无生产默认切换；无 7×24；compose 依赖本机 Docker daemon |
| Archive | [`ADR10_PHASE_C_RUNLOG.txt`](./ADR10_PHASE_C_RUNLOG.txt) |

## Priority

1. 停 compose / 清 volume：`docker compose -f compose.adr10-diagnosis-mvp.yml down -v`  
2. 清宿主沙箱：`rm -rf /tmp/aiplat-adr10-diag-home*`  
3. 禁用以本演练证明「已切生产默认」或对外 E4

```bash
bash scripts/adr10_diagnosis_mvp_phase_c.sh
AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash scripts/adr10_diagnosis_mvp_pilot.sh  # exit 3
docker compose -f compose.adr10-diagnosis-mvp.yml run --rm adr10-diagnosis-mvp
docker compose -f compose.adr10-diagnosis-mvp.yml down -v
```
