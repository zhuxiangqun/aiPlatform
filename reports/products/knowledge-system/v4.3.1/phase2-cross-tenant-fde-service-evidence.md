---
doc_type: Report
title: Phase 2 — FDE service GraphIndex 租户证据（N09 Batch K28）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / FDE service tenant（Batch K28）证据

> 实施权威：附录 N N09 partial 加深（FDE apps/service GraphIndex）。  
> **未宣称** core_facade 残余 / system / wiki_ontology_domains / evaluation / infra gates bare load / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 6 个 FDE service 文件无 bare load | pass | `test_fde_service_sources_wire_tenant` |
| rapid_insight helper | pass | `test_ri_graph_tenant_resolves` |
| ontology_pillars 透传 | pass | `test_ontology_pillars_loads_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fde_service_tenant_k28.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| k_wave_reason / abox / pillars / governance / clarify | `_resolve_graph_tenant()` → `GraphIndex.load(..., tenant_id=)` |
| rapid_insight_service | `_ri_graph_tenant()` → 5× load |

## 明确未做

- core_facade/system/eval/infra → 见 Batch K29；skills/registry/pipeline_engine bare load 仍残余
- clarify 中 `fde-delivery` 域名硬编码（仅补 tenant）
- N09 / 附录 N 全量认证
