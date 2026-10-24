# ADR-10 试点：诊断 MVP（Phase A）

> **批准**：`ADR10_DIAGNOSIS_MVP_WIRING_DECISION.md` · 场景 `fp-customer-lock-service-bundle-pi-diag-001`  
> **非目标**：拆控制面/FDE/全功能中台/全拆；改生产默认路径

## 允许路径

| 路径 | 允许 |
|------|:----:|
| `scripts/adr10_diagnosis_mvp*` · `reports/five-products/ADR10_*` · SCHEDULE | ✅ |
| compose（Phase B+）· 搬仓拆服务 · 强制改生产默认 | ❌ |

## 约定

- Env：`scripts/adr10_diagnosis_mvp.env.example`（可选 `.env.adr10-diagnosis-mvp`）  
- 数据：`AIPLAT_HOME=/tmp/aiplat-adr10-diag-home`；禁无授权写 `~/.aiplat`  
- API：仅既有 `ingest_slice_evidence_from_jsonl` / `build_slice_diagnosis_report`

```bash
bash scripts/adr10_diagnosis_mvp_pilot.sh
AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash scripts/adr10_diagnosis_mvp_pilot.sh  # exit 3
```
