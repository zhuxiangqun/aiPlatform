---
doc_type: Report
title: Phase 2 — Revision→ActionExecution 桥接证据（N24 Batch I4）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Revision Action Bridge（Batch I4）证据

> 实施权威：附录 N N24 partial 加深（审批式 restore 决策桥接到 ActionExecution）。  
> **未宣称** 回滚 UI / Package+Action 全量总线合并 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 批准创建 bridge + execution | pass | `test_approve_creates_bridge_and_execution` / suite |
| 桥接幂等 | pass | `test_bridge_idempotent` |
| 跨租户空 | pass | `test_cross_tenant_empty` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_revision_action_bridge_phase2.py -v
# 预期：4 passed
```

实测（2026-11-17）：`4 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 表 | `revision_action_bridge` |
| 写入 | `approve/reject_revision_restore` → `bridge_revision_audit_to_action` → `persist_execution` |
| 查询 | `list_revision_action_bridges` |
| 套件 | `run_revision_action_bridge_suite` / `evaluate_revision_action_bridge_gate` |
| Facade | `fact_ledger_list_revision_action_bridges` + suite/gate |

## 明确未做

- 管理端回滚/审计 UI
- Package/Action 全量统一审计总线合并
- 强制所有 revision archive 事件进 ActionExecution
- N24 / 附录 N 全量认证
