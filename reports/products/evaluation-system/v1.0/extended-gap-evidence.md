---
doc_type: Report
doc_id: EVAL_SYS_V10_EXT_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: 评测系统 v1.0 附录 N Extended（E07–E09）代码证据盘点；非 certified
---

# 评测系统 v1.0 — Extended 差距证据（测量）

> **性质**：测量报告。`exists` ≠ `certified` / ≠ `extended_ready` 正式徽章。  
> **刷新**：2026-11-26 Extended E07–E09 收口后。

## 总判定

| 问题 | 结论 |
|---|---|
| E07–E09 测量 | **exists** |
| 正式 extended_ready / certified | **否**（须非作者复核） |

## E07–E09

| ID | 状态 | 证据 | 缺口 |
|---|---|---|---|
| E07 Judge 校准报告 | **exists** | `judge_contract.normalize_judge_report`；`run_e4_calibration`；`eval_normalize_judge_report`；`test_judge_contract_e07.py` | κ / 双人标注仍属 Operational E12 |
| E08 评测中心 `/eval` | **exists** | `eval_center_route_contract`；`App.tsx` EvalCenter；`test_eval_center_route_e08.py` | — |
| E09 Tool/MCP subject | **exists** | `interop_subject.normalize_tool_mcp_subject`；`McpSubjectAdapter` 注册；外援须 `verified_tier`；`EvalCenter` tool-regression tab；`test_interop_subject_e09.py` | 非 first-class OBJECT_TYPES；live MCP accuracy 关闭 |

## 复现命令

```bash
pytest aiPlat-core/core/tests/unit/test_apps/test_judge_contract_e07.py \
  aiPlat-core/core/tests/unit/test_apps/test_eval_center_route_e08.py \
  aiPlat-core/core/tests/unit/test_apps/test_interop_subject_e09.py -q
```
