---
doc_type: Report
---

# Arena 本地产品决策（2026-11-06）

- **默认 runner**：保持 `arena` length smoke（`judge_kind=length_heuristic`，`quality_gate_eligible=false`）。
- **盲评 pilot**：仅作证据/报告展示；**不**替换默认 judge；**不**打开质量 gate。
- **原因**：pilot QA 未整体通过；本机优先可跑 smoke，不作偏好/质量胜负宣称。
- **诚实锁**：`accuracy_claim=false` · Center Arena tab = smoke enqueue + 诚实文案。

日后若重跑干净盲评并签 integrity，再单独立项决定是否 shadow 默认 judge。
