---
doc_type: Report
title: Phase 2 — ontology_engine GraphIndex 租户证据（N09 Batch K26）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / ontology_engine tenant（Batch K26）证据

> 实施权威：附录 N N09 partial 加深（OntologyEngine / get_graph / shard / cleanup / gap / action / business bridge）。  
> **未宣称** builtin_handlers / FDE service bare load / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| engine + get_graph 租户缓存键 | pass | `test_engine_source_wires_tenant` |
| 支撑模块全量 load tenant | pass | `test_supporting_modules_source_wires_tenant` |
| get_graph 按租户分缓存 | pass | `test_get_graph_caches_per_tenant` |
| cleanup 透传 | pass | `test_cleanup_loads_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ontology_engine_tenant_k26.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| OntologyEngine.process | `GraphIndex.load(..., tenant_id=self._tenant_id)` |
| get_graph | `cache_key=tid::domain` → `GraphIndex.load(..., tenant_id=tid)` |
| ShardedGraphIndex / cleanup / gap / run_context / action / business bridge | `tenant_id` / `_resolve_graph_tenant` |

## 明确未做

- builtin_handlers → 见 Batch K27；FDE service bare load 仍残余
- N09 / 附录 N 全量认证
