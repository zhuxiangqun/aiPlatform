# ADR-10 诊断 MVP — Rollback（Phase A–D2）

| Field | Value |
|-------|-------|
| Scene | `fp-customer-lock-service-bundle-pi-diag-001` |
| Date | 2026-10-24（A–B）· 2026-10-26 Phase C/D/D2 |
| Result | **PASS** — C 宿主+compose；D1 共享 home；D2 签收默认绑定 |
| Residual | 无 compose 长驻；无 7×24；无 E4 / 全拆 |
| Archive | [`ADR10_PHASE_C_RUNLOG.txt`](./ADR10_PHASE_C_RUNLOG.txt) · [`ADR10_PHASE_D_RUNLOG.txt`](./ADR10_PHASE_D_RUNLOG.txt) · D2 摘录见 [`ADR10_DIAGNOSIS_MVP_D2_DECISION.md`](./ADR10_DIAGNOSIS_MVP_D2_DECISION.md) |

## Priority

1. **D2 回滚**：`export AIPLAT_DIAGNOSIS_PROD_DEFAULT=0`（签收恢复仅 `fp-*`/`for_slice` 强制）  
2. **Phase D1 回滚**：`unset AIPLAT_DIAGNOSIS_PROD_DEFAULT ADR10_ALLOW_USER_HOME`；可选 `rm -rf ~/.aiplat/adr10-diagnosis-mvp-d1`  
3. 停 compose / 清 volume：`docker compose -f compose.adr10-diagnosis-mvp.yml down -v`  
4. 清宿主沙箱：`rm -rf /tmp/aiplat-adr10-diag-home*`  
5. 禁用以本演练证明对外 E4 / 全拆 / compose 长驻

```bash
ADR10_PHASE=d2 bash scripts/adr10_diagnosis_mvp_phase_d.sh
ADR10_PHASE=d1 bash scripts/adr10_diagnosis_mvp_phase_d.sh
AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash scripts/adr10_diagnosis_mvp_pilot.sh  # exit 3（无 ALLOW_USER_HOME）
bash scripts/adr10_diagnosis_mvp_phase_c.sh
docker compose -f compose.adr10-diagnosis-mvp.yml down -v
```
