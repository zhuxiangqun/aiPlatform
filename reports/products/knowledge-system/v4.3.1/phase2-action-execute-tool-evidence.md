---
doc_type: Report
title: Phase 2 — action.execute Agent Tool 最小切片证据（W6）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / action.execute（W6）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W6。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §F.2 / §G。  
> **未宣称**附录 N 全量符合；仅证明 Agent 工具经 ActionRegistry L1 执行且禁 bypass。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 禁 SQL/直写 | pass | `test_execute_rejects_sql` |
| 禁 `_bypass_approval` | pass | `test_execute_rejects_bypass_approval` |
| `action_id` + entity 必填 | pass | `test_execute_requires_action_and_entity` |
| 经 CoreFacade ActionRegistry | pass | `test_execute_delegates_to_facade` |
| 缺权限透传拒绝 | pass | `test_execute_policy_denied` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_action_execute_tool_phase2.py -v
# 预期：5 passed
```

实测（2026-11-16）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| Tool | `ActionExecuteTool`（`action.execute`） |
| 注册 | `server.py` ToolRegistry seed |
| Facade | `execute_action` → `AsyncActionRegistry.execute`（无 bypass） |

## 明确未做（后续）

- SDK 生成 → 见 `phase2-sdk-evidence.md`（本批另切片）
- 字段级 ACL；附录 N 全量符合
- ActionExecution 幂等账本 → 见 `phase2-action-execution-evidence.md`（W7）
- 新动作合同设计（复用已有 ActionRegistry / confirm 等）
