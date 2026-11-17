---
doc_type: Report
title: Phase 2 — 审批式 Restore 证据（N24 Batch I3）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Restore Approval（Batch I3）证据

> 实施权威：附录 N N24 partial 加深（ledger 内请求/批准/拒绝 restore）。  
> **未宣称** 回滚 UI / Package+Action 统一审计总线 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 请求创建 pending | pass | `test_request_and_self_approve_rejected` / suite |
| 自批拒绝 | pass | `test_request_and_self_approve_rejected` |
| 批准执行 restore | pass | `test_approve_applies_restore` |
| 拒绝不改头 | pass | `test_reject_leaves_head` |
| 重复 pending 拒绝 | pass | `test_duplicate_pending_rejected` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_restore_approval_phase2.py -v
# 预期：5 passed
```

实测（2026-11-17）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 表 | `revision_restore_requests` |
| API | `request_revision_restore` / `approve_revision_restore` / `reject_revision_restore` / `list_revision_restore_requests` |
| 审计 | `restore_request` / `restore_approve` / `restore_reject` 写入 `revision_audit` |
| 套件 | `run_restore_approval_suite` / `evaluate_restore_approval_gate` |
| Facade | `fact_ledger_request/list/approve/reject_revision_restore` + suite/gate |

## 明确未做

- 管理端回滚/审批 UI
- Package+Action 统一审计总线合并
- 直连 `restore_*` 强制审批（仍保留程序化直调）
- N24 / 附录 N 全量认证
