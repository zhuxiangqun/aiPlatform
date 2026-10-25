# ADR-10 接线 Phase B — 诊断 MVP compose 容器试点

- **状态**：**已批（本批）** · 2026-10-24  
- **依据**：ADR-10 决策 §5；Phase A 已合入 `#415`  
- **触发**：「继续」  
- **决策人**：架构 × 业务 × 诊断 R（兼任）

## 范围

| 项 | 本批 |
|----|:----:|
| `compose.adr10-diagnosis-mvp.yml` 一键容器跑 Phase A 烟测 | ✅ |
| 更新试点边界 / 回滚（`compose down`） | ✅ |
| 改生产默认路径 / 长驻诊断微服务 / 拆库 / ADR-09 / E4 | ❌ |

## DoD

1. `compose.adr10-diagnosis-mvp.yml` 合入；`AIPLAT_DIAGNOSIS_PROD_DEFAULT` 固定 `"0"`  
2. 宿主 `bash scripts/adr10_diagnosis_mvp_pilot.sh` → PASS（本批）  
3. compose `run --rm`：须 PASS（slim 内 `pip install` 最小依赖后跑宿主同款烟测）  
4. 回滚：`docker compose -f compose.adr10-diagnosis-mvp.yml down -v`

签署：架构 × 业务 × 诊断 R（兼任）· 2026-10-24  
