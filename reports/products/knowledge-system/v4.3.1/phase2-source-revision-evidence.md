---
doc_type: Report
title: Phase 2 — Source Revision 最小账本证据（N24 Batch H2）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Source Revision（Batch H2）证据

> 实施权威：附录 N N24 partial 加深（G2/H1 Fact/Claim revision 对称的 Source 切片）。  
> **未宣称** 一键回滚 UI / Package+Action 统一审计总线 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无抬号内容覆盖拒绝 | pass | `test_overwrite_without_revision_bump_rejected` / suite |
| 变更归档旧快照 | pass | `test_revision_archived_on_update` |
| 按 revision 读回 + diff | pass | `test_get_and_diff_source_revisions` |
| 同内容幂等 | pass | `test_same_content_idempotent` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_source_revision_phase2.py -v
# 预期：5 passed
```

实测（2026-11-17）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `source_revisions` 表 + `list_source_revisions` / `get_source_at_revision` / `diff_source_revisions` |
| 写入 | `register_source` 内容变更强制 revision bump + 归档；旧 Raw 文件保留 |
| 套件 | `run_source_revision_suite` / `evaluate_source_revision_gate` |
| Facade | `fact_ledger_list_source_revisions` / `get_source_at_revision` / `diff_source_revisions` + suite/gate |

## 明确未做

- 一键回滚写回 / 审批式 revert 工作流
- Package+Action 审计总线合并
- 连接器矩阵全量 / 活 URI 热更新
- N24 / 附录 N 全量认证
