---
doc_type: Report
title: Phase 2 — ActionExecution 最小切片证据（W7 / C.2）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / ActionExecution（W7）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W7。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §C.2。  
> **未宣称**附录 N 全量符合；仅证明 customer_action 幂等键 + before/after 最小切片。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| platform_action 不强制幂等键 | pass | `test_require_keys_platform_passthrough` |
| customer 缺 tenant/key → invalid | pass | `test_require_keys_customer_missing` / `test_run_customer_missing_keys` |
| 首次执行落盘 before/after | pass | `test_run_customer_idempotent_replay` |
| 重复键 idempotent_replay 不重跑 | pass | `test_run_customer_idempotent_replay` |
| 冲突写不改历史 | pass | `test_persist_and_lookup_idempotent` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_action_execution_phase2.py -v
# 预期：5 passed
```

实测（2026-11-16）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `action_execution.run_customer_action_with_execution` |
| Facade | `execute_action`（customer_action 分支）+ `lookup_action_execution` |
| Tool | `ActionExecuteTool` 合并顶层 tenant/idempotency → params |
| HTTP | `POST …/actions/execute` → `facade_execute_action`（不再直调 Registry） |
| HTTP 查询 | `GET …/actions/executions/lookup` → `lookup_action_execution` |

## 明确未做（后续）

- kill switch / Lv4 误报门重设计
- 字段级 ACL（W8）
- 取消 Registry 内审批通过后的 `_bypass_approval`（如 confirm / assert_inferred_edge）
- StateMachine → ActionRegistry 桥（`ontology_engine/engine.py`）仍直调 Registry；未纳入本切片
- 附录 N 全量符合
