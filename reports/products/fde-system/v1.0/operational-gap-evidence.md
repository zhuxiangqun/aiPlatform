---
doc_type: Report
doc_id: FDE_SYS_V10_OPS_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: FDE 系统 v1.0 Operational（F10–F11）测量；默认未授权；不扩大 ADR-09
---

# FDE 系统 v1.0 — Operational 差距证据（测量）

| ID | 状态 | 证据 |
|---|---|---|
| F10 生产独立进程 authorize | **exists** | `evaluate_fde_production_process_authorize`；`AIPLAT_FDE_OPTIONAL_SPLIT` 不够 |
| F11 compose 长驻 | **exists** | `evaluate_fde_compose_long_running_authorize`；须批准 + `adr_ref`；标准正文未授权 |

**当前 authorized=false。compose 长驻=否。**

```bash
pytest aiPlat-core/core/tests/unit/test_apps/test_fde_operational_f10_f11.py -q
```
