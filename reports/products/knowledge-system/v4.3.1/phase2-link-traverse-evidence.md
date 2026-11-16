---
doc_type: Report
title: Phase 2 — link.traverse 最小切片证据（W6）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / link.traverse（W6）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W6。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §F.2。  
> **未宣称**附录 N 全量符合；仅证明多跳只读 + 租户前置 + L1 + 禁 SQL/直写。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 缺 `kb:read` 拒绝 | pass | `policy_denied`；`test_policy_denied_without_kb_read` |
| 租户隔离 | pass | t2 边不可见；`test_tenant_isolation` |
| `max_hops` 生效 | pass | `test_max_hops_one` |
| `link_types` 过滤 | pass | `test_link_type_filter` |
| Agent 工具禁 SQL | pass | `test_tool_rejects_sql` |
| 经 CoreFacade | pass | `_facade_traverse_links`；`test_tool_delegates_to_facade` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_link_traverse_phase2.py -v
# 预期：6 passed
```

实测（2026-11-16）：`6 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `harness/knowledge_pipeline/link_traverse.py` → `traverse_links` |
| Facade | `traverse_object_links` |
| Tool | `LinkTraverseTool`（`link.traverse`）+ `server.py` seed |
| HTTP | `POST …/fde/links/traverse` |

## 明确未做（后续）

- `action.execute` / `object_set.aggregate` / SDK 生成
- GraphIndex 写路径；字段级 ACL
- 附录 N 全量符合
