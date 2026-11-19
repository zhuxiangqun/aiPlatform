---
doc_type: Report
title: Phase 2 — evolver/SECI/retrieval GraphIndex 租户证据（N09 Batch K22）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / evolver · SECI · retrieval tenant（Batch K22）证据

> 实施权威：附录 N N09 partial 加深（演化/SECI/编排检索/路径/候选池）。  
> **未宣称** diagnostician/convergence/case_learning/recon 等其它 GraphIndex 调用面 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| system_evolver 全量 load tenant | pass | `test_system_evolver_source_wires_tenant` |
| seci_engine + post_loop tenant | pass | `test_seci_engine_source_wires_tenant` |
| orchestrated_retrieval tenant | pass | `test_orchestrated_retrieval_source_wires_tenant` |
| path_planner tenant | pass | `test_path_planner_source_wires_tenant` |
| candidate_pool tenant | pass | `test_candidate_pool_source_wires_tenant` |
| evolver init 解析租户 | pass | `test_system_evolver_init_resolves_tenant` |
| execute_path 透传 | pass | `test_execute_path_loads_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_evolver_seci_retrieval_tenant_k22.py -v
# 预期：7 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| SystemEvolver / SECIEngine | `__init__(tenant_id=)` → `_resolve_graph_tenant` → `GraphIndex.load(..., tenant_id=)` |
| orchestrated_retrieval | `traverse_ontology_graph` / `ontology_first_retrieve(tenant_id=)` |
| path_planner | `execute_path(..., tenant_id=)` |
| candidate_pool | gap 校验 `_resolve_graph_tenant()` |

## 明确未做

- system_diagnostician / convergence_engine / ontology_case_learning / recon_subgraph → 见 Batch K23
- N09 / 附录 N 全量认证
