---
doc_type: Report
title: Phase 2 — Agent Tool 最小切片证据（W6）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Agent Tool（W6）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W6。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §F.2。  
> **未宣称**附录 N 全量符合；仅证明 `object.query` / `function.call` 经 Facade + 禁 SQL/直写。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `sql` / `write_fact` 入参拒绝 | pass | `sql_or_write_forbidden`；`test_object_query_rejects_sql` / `test_function_call_rejects_write_key` |
| `tenant_id` 必填（object.query） | pass | `tenant_id_required`；`test_object_query_requires_tenant` |
| 经 CoreFacade ObjectSet | pass | `_facade_query_object_set`；`test_object_query_delegates_to_facade` |
| 缺 `kb:read` 透传拒绝 | pass | `policy_denied`；`test_object_query_policy_denied` |
| function.call 经 Facade | pass | `_facade_invoke_function`；`test_function_call_ok` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:. python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_agent_tool_phase2.py -v
# 预期：6 passed
```

实测（2026-11-16）：`6 passed in 0.14s`。

## 接线

| 入口 | 路径 |
|------|------|
| Tools | `apps/tools/knowledge_agent_tools.py` → `ObjectQueryTool` / `FunctionCallTool` |
| 注册 | `core/server.py` ToolRegistry seed |
| Facade | `query_object_set` / `invoke_function` |

## 明确未做（后续）

- `link.traverse` / `action.execute` / `object_set.aggregate`
- SDK 生成；字段级 ACL
- 附录 N 全量符合
