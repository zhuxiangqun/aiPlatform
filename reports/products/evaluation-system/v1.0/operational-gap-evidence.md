---
doc_type: Report
doc_id: EVAL_SYS_V10_OPS_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: 评测系统 v1.0 Operational（E10–E12）测量；默认未授权
---

# 评测系统 v1.0 — Operational 差距证据（测量）

> **性质**：门禁/报告存在性测量。`exists` ≠ `authorized` ≠ `certified`。  
> 批准模板：`operational-approval-record.pending.json`（status=pending）。

## 总判定

| 问题 | 结论 |
|---|---|
| E10–E12 能力存在 | **exists** |
| 当前 authorized / operational_ready | **false**（无非作者批准） |
| certified | **否** |

## E10–E12

| ID | 状态 | 证据 |
|---|---|---|
| E10 A3 process_split | **exists** | `evaluate_eval_process_split_authorize`；env 单独打开不够；默认 false |
| E11 生产 SLA authorize | **exists** | `evaluate_eval_production_sla_authorize`；须批准 + `sla_ref` |
| E12 双人 κ | **exists** | `build_dual_annotator_kappa_report`（inter_annotator；`accuracy_claim=false`） |

## 复现

```bash
pytest aiPlat-core/core/tests/unit/test_apps/test_eval_operational_e10_e12.py -q
```
