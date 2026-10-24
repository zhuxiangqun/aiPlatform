# ADR-10 接线 Phase A — 诊断 MVP 沙箱试点

- **状态**：**已批** · 2026-10-24  
- **依据**：ADR-10 决策 §5（清单 + env；**禁**改生产默认路径）  
- **触发**：#413/#414 后「继续」

## 范围

| 项 | 本批 |
|----|:----:|
| 试点边界 + 回滚模板 | ✅ |
| 独立 env + 隔离 `AIPLAT_HOME` 烟测 | ✅ |
| 改生产默认 / compose 长驻 / 新微服务 / ADR-09 / E4 | ❌ |

## DoD

1. `scripts/adr10_diagnosis_mvp.env.example`；`AIPLAT_DIAGNOSIS_PROD_DEFAULT=1` → exit 3  
2. `bash scripts/adr10_diagnosis_mvp_pilot.sh` → ingest→report PASS（场景 `fp-customer-lock-service-bundle-pi-diag-001`）  
3. 回滚：删沙箱 home；控制面不变  

签署：架构 × 业务 × 诊断 R（兼任）· 2026-10-24  
