---
doc_type: Report
title: Phase 2 — wiki_ontology_engine GraphIndex 租户证据（N09 Batch K25）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / wiki_ontology_engine tenant（Batch K25）证据

> 实施权威：附录 N N09 partial 加深（wiki ontology engine 路由 GraphIndex）。  
> **未宣称** ontology_engine.engine / builtin_handlers / FDE service bare load / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| wiki_ontology_engine 10 处 load tenant | pass | `test_wiki_ontology_engine_source_wires_tenant` |
| `_graph_tenant` 解析 | pass | `test_graph_tenant_helper_resolves` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_wiki_ontology_engine_tenant_k25.py -v
# 预期：2 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| wiki_ontology_engine.py | `_graph_tenant()` → `_resolve_graph_tenant` → `GraphIndex.load(..., tenant_id=)`（10 处） |

## 明确未做

- ontology_engine → 见 Batch K26；builtin_handlers / FDE service bare load 仍残余
- sync-all 端点按全局 graph 目录枚举的多租户物理隔离深化
- N09 / 附录 N 全量认证
