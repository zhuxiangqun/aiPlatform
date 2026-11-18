---
doc_type: Report
title: Phase 2 — KB/tracking domain request fallbacks 去硬编码证据（N09 Batch K43）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / KB·tracking request fallbacks（Batch K43）证据

> 实施权威：附录 N N09 partial 加深（请求/状态 `ai-knowledge`/`fde-delivery`/`default` 回落 → DomainRouter helpers）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| wiki_ontology_engine 请求回落 | pass | `test_wiki_ontology_engine_req_fallbacks_use_helper` |
| facade/pipeline/agents HITL | pass | `test_facade_pipeline_agents_kb_fallback` |
| action_routes tracking | pass | `test_action_routes_tracking_fallback` |
| retrieval circuit breaker | pass | `test_retrieval_circuit_breaker_graph_domain` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_kb_domain_fallbacks_k43.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| wiki_ontology_engine | `_kb_domain` / `_req_domain_id` → `default_kb_domain()` |
| core_facade auto ontology | `router.default_kb_domain()` |
| pipeline_engine HITL / agents grilling | `default_kb_domain()` |
| action_routes list | `fde_graph_domain()` |
| retrieval wiki circuit breaker | `default_graph_domain()` |

## 明确未做

- 函数签名默认参数 `domain_id: str = "ai-knowledge"` → 见 Batch K44
- icebreaker_map 业务域键
- `tenant_id or "default"` 租户回落
- N09 certified（仍 false）
