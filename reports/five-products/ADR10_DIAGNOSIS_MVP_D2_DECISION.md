# ADR-10 D2 决定 — 平台默认绑定（签收入口）

- **状态**：**Accepted（窄）** · 2026-10-26  
- **批准句**（用户）：批准 ADR-10 D2（平台默认绑定）：入口为 ___ ；回滚 `AIPLAT_DIAGNOSIS_PROD_DEFAULT=0`。接受兼任。不含 E4 / 全拆。  
- **入口填空（本决定）**：`POST /api/platform/apps/fde/acceptance/signoff` → `validate_slice_signoff_reports`（`slice_evidence.py`）  
- **不含**：compose 长驻 profile；对外 E4；ADR-09 Accepted / 全拆；拆 FDE / 新诊断中台

## 行为

| flag | 行为 |
|------|------|
| `AIPLAT_DIAGNOSIS_PROD_DEFAULT=1` | 上述签收入口**一律**要求有效 `evidence_report_ids`（不仅 `fp-*` / `for_slice`） |
| `=0`（回滚） | 恢复 Gate3 D 规则：仅 `fp-*` / `for_slice` / 显式 ids 强制 |
| `AIPLAT_FDE_REQUIRE_DIAG_REPORT_FOR_SLICE=0` | 总开关仍可整段关闭（应急） |

## 验证

1. `pytest aiPlat-core/core/tests/apps/fde/test_slice_five_products.py -k signoff -q` → 4 passed  
2. `ADR10_PHASE=d2 bash scripts/adr10_diagnosis_mvp_phase_d.sh` → PASS（PROD_DEFAULT=1 强制；`=0` 回滚）  
3. 回滚：`AIPLAT_DIAGNOSIS_PROD_DEFAULT=0` → legacy `spec_id` 无 report 仍可签收

### Smoke 摘录（20261026T045659Z）

```
PASS: PROD_DEFAULT=1 binding
PASS: PROD_DEFAULT=0 rollback
PASS: ADR-10 Phase D2 complete
```

## 签署

架构 × 业务 × 诊断 R（兼任）· 2026-10-26 · **仅 D2 签收默认绑定；E4/全拆仍须另批**
