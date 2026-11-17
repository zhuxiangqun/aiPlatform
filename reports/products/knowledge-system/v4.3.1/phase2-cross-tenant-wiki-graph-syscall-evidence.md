---
doc_type: Report
title: Phase 2 — wiki / graph syscall GraphIndex 租户证据（N09 Batch K24）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / wiki · graph syscall tenant（Batch K24）证据

> 实施权威：附录 N N09 partial 加深（wiki 路由 GraphIndex + sys_graph_neighbors / sys_graph_validate）。  
> **未宣称** wiki_ontology_engine / ontology_engine.engine / FDE 业务面等其它 bare load / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| wiki.py 全量 load tenant | pass | `test_wiki_router_source_wires_tenant` |
| sys_graph_neighbors tenant | pass | `test_sys_graph_neighbors_source_wires_tenant` |
| sys_graph_validate tenant | pass | `test_sys_graph_validate_source_wires_tenant` |
| neighbors 透传 | pass | `test_sys_graph_neighbors_loads_tenant` |
| validate 透传 | pass | `test_sys_graph_validate_loads_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_wiki_graph_syscall_tenant_k24.py -v
# 预期：5 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| wiki.py GraphIndex | `_resolve_graph_tenant()` → `GraphIndex.load(..., tenant_id=)` |
| sys_graph_neighbors / sys_graph_validate | `tenant_id=` → `_resolve_graph_tenant` → load |

## 明确未做

- wiki_ontology_engine → 见 Batch K25；ontology_engine.engine / FDE service bare load 仍残余
- N09 / 附录 N 全量认证
