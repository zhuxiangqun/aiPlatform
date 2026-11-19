---
doc_type: Report
title: Phase 2 — GraphIndex ctor domain 去硬编码证据（N09 Batch K42）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / GraphIndex ctor domain（Batch K42）证据

> 实施权威：附录 N N09 partial 加深（`GraphIndex("ai-knowledge"|"default")` → DomainRouter helpers）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| default_graph_domain ≠ default_kb_domain | pass | `test_domain_router_default_graph_domain` |
| 目标文件走 helpers | pass | `test_targets_use_domain_router_helpers` |
| 生产 ctor 域字面量空 | pass | `test_production_graphindex_ctor_domain_literals_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_graphindex_ctor_domain_k42.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter | `PLATFORM_DEFAULT_GRAPH_DOMAIN` + `default_graph_domain()` |
| hallucination_tracker | `default_kb_domain()` |
| doc_quality_monitor / retrieval early-exit | `default_graph_domain()` |

## 明确未做

- `tenant_id or "default"` 租户回落字面量（非 ontology domain）
- icebreaker_map 业务域键字面量
- 函数默认参数 `domain_id: str = "ai-knowledge"` 等签名默认值
- N09 / 附录 N 全量认证（certified 仍 false）
