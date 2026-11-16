---
doc_type: Report
title: Phase 2 — object_set.aggregate Agent Tool 最小切片证据（W6）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / object_set.aggregate（W6）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W6。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §F.2 / §E。  
> **未宣称**附录 N 全量符合；仅证明 Agent 工具经 ObjectSet 只读 count 聚合。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 禁 SQL/直写 | pass | `test_aggregate_rejects_sql` |
| `aggregate` 必填 | pass | `test_aggregate_requires_specs` |
| 仅 `count` | pass | `test_aggregate_type_must_be_count` |
| 经 CoreFacade ObjectSet | pass | `test_aggregate_delegates_to_facade` |
| 缺 `kb:read` 透传拒绝 | pass | `test_aggregate_policy_denied` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_object_set_aggregate_tool_phase2.py -v
# 预期：5 passed
```

实测（2026-11-16）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| Tool | `ObjectSetAggregateTool`（`object_set.aggregate`） |
| 注册 | `server.py` ToolRegistry seed |
| Facade | `query_object_set`（复用；请求带 `aggregate`） |

## 明确未做（后续）

- `sum`/`avg` 等非 count 聚合；SDK
- `action.execute` → 见 `phase2-action-execute-tool-evidence.md`（本批另切片）
- 字段级 ACL；附录 N 全量符合
