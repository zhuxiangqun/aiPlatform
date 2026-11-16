---
doc_type: Report
title: Phase 2 — Fact Revision 最小账本证据（N24 Batch G2）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Fact Revision（Batch G2）证据

> 实施权威：附录 N N24 partial 加深（统一 Fact Revision 账本最小切片）。  
> **未宣称** Claim 全历史 / 一键回滚 UI / Package+Action 统一审计总线 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无抬号覆盖拒绝 | pass | `test_overwrite_without_revision_bump_rejected` / suite |
| 变更归档旧快照 | pass | `test_revision_archived_on_update` |
| 按 revision 读回 + diff | pass | `test_get_and_diff_revisions` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_revision_phase2.py -v
# 预期：4 passed
```

实测（2026-11-17）：`4 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `fact_revisions` 表 + `list_fact_revisions` / `get_fact_at_revision` / `diff_fact_revisions` |
| 写入 | `put_fact` 内容变更强制 revision bump + 归档 |
| 套件 | `run_fact_revision_suite` / `evaluate_fact_revision_gate` |
| Facade | `fact_ledger_list_revisions` / `get_at_revision` / `diff_revisions` + suite/gate |
| Transition | `transition_fact_*` 透传 `revision_actor`/`revision_reason` |

## 明确未做

- Claim / Source 统一 revision 账本
- 一键回滚写回 / 审批式 revert 工作流
- Package+Action 审计总线合并
- N24 / 附录 N 全量认证
