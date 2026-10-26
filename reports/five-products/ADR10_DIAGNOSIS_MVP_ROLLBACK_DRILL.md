# ADR-10 诊断 MVP — Rollback（Phase A–D）

| Field | Value |
|-------|-------|
| Scene | `fp-customer-lock-service-bundle-pi-diag-001` |
| Date | 2026-10-24（A–B）· 2026-10-26 Phase C/D |
| Result | **PASS** — C 宿主+compose；D1 共享 home opt-in（`rep-29d565cf2f5b`） |
| Residual | 无 D2 平台默认绑定；无 7×24；无 E4 |
| Archive | [`ADR10_PHASE_C_RUNLOG.txt`](./ADR10_PHASE_C_RUNLOG.txt) · [`ADR10_PHASE_C_COMPOSE_RERUN.txt`](./ADR10_PHASE_C_COMPOSE_RERUN.txt) · [`ADR10_PHASE_D_RUNLOG.txt`](./ADR10_PHASE_D_RUNLOG.txt) |

## Priority

1. **Phase D 回滚**：`unset AIPLAT_DIAGNOSIS_PROD_DEFAULT ADR10_ALLOW_USER_HOME`；可选 `rm -rf ~/.aiplat/adr10-diagnosis-mvp-d1`  
2. 停 compose / 清 volume：`docker compose -f compose.adr10-diagnosis-mvp.yml down -v`  
3. 清宿主沙箱：`rm -rf /tmp/aiplat-adr10-diag-home*`  
4. 禁用以本演练证明 D2 / 对外 E4 / 全拆

```bash
bash scripts/adr10_diagnosis_mvp_phase_d.sh
AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash scripts/adr10_diagnosis_mvp_pilot.sh  # exit 3
bash scripts/adr10_diagnosis_mvp_phase_c.sh
docker compose -f compose.adr10-diagnosis-mvp.yml down -v
```
