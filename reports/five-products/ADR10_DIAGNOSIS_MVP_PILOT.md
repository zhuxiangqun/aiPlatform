# ADR-10 试点：诊断 MVP（Phase A–C）

> **批准**：A `ADR10_DIAGNOSIS_MVP_WIRING_DECISION.md`；B `ADR10_DIAGNOSIS_MVP_PHASE_B_DECISION.md`；C `ADR10_DIAGNOSIS_MVP_PHASE_C_DECISION.md`  
> **场景**：`fp-customer-lock-service-bundle-pi-diag-001`  
> **非目标**：拆控制面/FDE/全功能中台/全拆；改生产默认路径；对外 E4

## 允许路径

| 路径 | 允许 |
|------|:----:|
| `scripts/adr10_diagnosis_mvp*` · `reports/five-products/ADR10_*` · SCHEDULE | ✅ |
| 仓库根 `compose.adr10-diagnosis-mvp.yml`（Phase B） | ✅ |
| Phase C 双端加深 `adr10_diagnosis_mvp_phase_c.sh` | ✅ |
| 搬仓拆服务 · 强制改生产默认 · 长驻诊断微服务 | ❌ |

## 约定

- Env：`scripts/adr10_diagnosis_mvp.env.example`（可选 `.env.adr10-diagnosis-mvp`）  
- 数据：沙箱 `AIPLAT_HOME`（宿主 `/tmp/...` 或 compose volume；Phase C 每轮隔离目录）  
- API：仅既有 ingest / `build_slice_diagnosis_report`

```bash
bash scripts/adr10_diagnosis_mvp_pilot.sh
bash scripts/adr10_diagnosis_mvp_phase_c.sh
docker compose -f compose.adr10-diagnosis-mvp.yml run --rm adr10-diagnosis-mvp
AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash scripts/adr10_diagnosis_mvp_pilot.sh  # exit 3
```
