---
doc_type: Report
title: Phase 2 — diagnostician/convergence/case/recon GraphIndex 租户证据（N09 Batch K23）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / diagnostician · convergence · case · recon tenant（Batch K23）证据

> 实施权威：附录 N N09 partial 加深（诊断/收敛/案例学习/侦察子图 merge）。  
> **未宣称** wiki/syscalls/engine 等其它 GraphIndex 调用面 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| system_diagnostician 全量 load tenant | pass | `test_system_diagnostician_source_wires_tenant` |
| convergence_engine tenant | pass | `test_convergence_engine_source_wires_tenant` |
| ontology_case_learning tenant | pass | `test_ontology_case_learning_source_wires_tenant` |
| recon_subgraph merge_to tenant | pass | `test_recon_subgraph_source_wires_tenant` |
| diagnostician init 解析租户 | pass | `test_diagnostician_init_resolves_tenant` |
| convergence init 解析租户 | pass | `test_convergence_init_resolves_tenant` |
| merge_to 透传 | pass | `test_recon_merge_to_loads_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_diagnostician_convergence_tenant_k23.py -v
# 预期：7 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| SystemDiagnostician / ConvergenceEngine | `__init__(tenant_id=)` → `_resolve_graph_tenant` → `GraphIndex.load(..., tenant_id=)` |
| OntologyCaseStore | `__init__(..., tenant_id=)` → case 图写入 |
| ReconSubgraph | `merge_to(..., tenant_id=)` → 目标域 `GraphIndex.load` |
| `_record_heal_audit` | 模块级 `_resolve_graph_tenant()` |

## 明确未做

- wiki / syscalls/graph → 见 Batch K24；wiki_ontology_engine / ontology_engine.engine 等仍残余
- N09 / 附录 N 全量认证
