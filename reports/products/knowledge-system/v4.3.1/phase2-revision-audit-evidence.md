---
doc_type: Report
title: Phase 2 — Revision Audit 账本内事件证据（N24 Batch I2）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Revision Audit（Batch I2）证据

> 实施权威：附录 N N24 partial 加深（抬号/restore 的 append-only 审计事件）。  
> **未宣称** 回滚 UI / 审批式 revert / Package+Action 统一审计总线 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| archive 写入 audit | pass | `test_archive_emits_audit` / suite |
| restore 写入 audit | pass | `test_restore_emits_audit` |
| 跨租户空结果 | pass | `test_cross_tenant_empty` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_revision_audit_phase2.py -v
# 预期：4 passed
```

实测（2026-11-17）：`4 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 表 | `revision_audit`（append-only） |
| 写入 | `_archive_*` → `archive`；`restore_*` 成功 → `restore` |
| 查询 | `list_revision_audit`（租户前置 + 可选过滤） |
| 套件 | `run_revision_audit_suite` / `evaluate_revision_audit_gate` |
| Facade | `fact_ledger_list_revision_audit` + suite/gate |

## 明确未做

- 管理端审计 UI
- 审批式 revert 工作流
- Package+Action 统一审计总线合并
- N24 / 附录 N 全量认证
