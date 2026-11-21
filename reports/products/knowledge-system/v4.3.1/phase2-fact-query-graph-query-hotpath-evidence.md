---
doc_type: Report
title: Phase 2 — Fact/Query graph_query 热路径加深证据（N19）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 graph_query 审计热路径证据

> 实施权威：附录 N N19 partial 加深（补齐导出但缺失的 `sys_graph_query` + MaterialsChat 透传落 Query 快照）。  
> **未宣称** N19 certified / 全部旁路强制 / 全量图查询 DSL。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `sys_graph_query` 已定义（stats/classes） | pass | `graph.py` |
| 显式 `tenant_id` → `maybe_record_wiki_kb_hotpath` | pass | channel=`graph_query` |
| MaterialsChat 透传 tenant | pass | graph context 注入 |
| suite `graph_query_hotpath_entry` | pass | `run_fact_query_audit_suite` |
| 行为测有 tenant 落盘 / 空跳过 | pass | `test_graph_query_hotpath` |
| certified 恒 false | pass | 回执 + suite/gate |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Agent syscall | `sys_graph_query(operation=stats\|classes, tenant_id=)` |
| MaterialsChat | 图谱摘要注入透传 tenant |
| 审计 | `maybe_record_wiki_kb_hotpath` channel=`graph_query` |

## 明确未做

- 全量图查询 DSL / Cypher
- 全部旁路 / N19 certified
