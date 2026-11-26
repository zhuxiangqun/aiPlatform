---
doc_type: Report
doc_id: EXT_INTEROP_V10_OPS_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: 外援互通 v1.0 Operational（X10–X11）测量；默认未授权
---

# 外援互通 v1.0 — Operational 差距证据（测量）

| ID | 状态 | 证据 |
|---|---|---|
| X10 生产 authorize | **exists** | `evaluate_interop_production_authorize`；默认 false |
| X11 供应商 SLA | **exists** | `bind_supplier_sla`；须批准 + `sla_ref` |

**当前 `operational_ready=true`**（朱莹非作者批准 `operational-approval-record.approved.json`）。≠ certified。pending 模板仍保留。

```bash
pytest aiPlat-core/core/tests/unit/test_skills/test_interop_operational_x10_x11.py -q
```
