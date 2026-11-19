---
doc_type: Report
title: Phase 2 — context_bus/system_health GraphIndex 租户证据（N09 Batch K21）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / context_bus · system_health tenant（Batch K21）证据

> 实施权威：附录 N N09 partial 加深（上下文注入 + 健康分审计）。  
> **未宣称** N09 certified（evolver/SECI/retrieval 见 K22）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| context_bus `_resolve_graph_tenant` + 全量 load tenant | pass | `test_context_bus_source_wires_tenant` |
| system_health 审计/缺口聚合全租户 | pass | `test_system_health_source_aggregates_tenants` |
| params tenant 优先 | pass | `test_resolve_graph_tenant_prefers_params` |
| graph_traversal 透传 | pass | `test_inject_graph_traversal_loads_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_context_bus_health_tenant_k21.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| context_bus | `_resolve_graph_tenant(params\|ActiveRequestContext)` → `GraphIndex.load(..., tenant_id=)` |
| system_health | `list_kb_tenant_ids()` → `audit_all_domains(tenant_id=)` / gap `GraphIndex.load` |

## 明确未做

- system_evolver / SECI / orchestrated_retrieval / path_planner / candidate_pool → **K22 已加深**（本文件保留 K21 范围陈述）
- N09 / 附录 N 全量认证
