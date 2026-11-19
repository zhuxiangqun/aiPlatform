---
doc_type: Report
title: Phase 2 — domain_id 运行时回退 SSOT（N09 Batch K63）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / domain_id runtime fallbacks（Batch K63）证据

> 实施权威：附录 N N09 partial 加深（FDE extraction/action/services + knowledge_pipeline/ontology/agents/diagnostics/wiki + CRAG 运行时 `domain_id or "default"` → `DomainRouter.default_graph_domain()`；helper 升为 `@classmethod`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定（classmethod） | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_domain_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_domain_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_domain_runtime_fallbacks_k63.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter | `default_graph_domain` → `@classmethod` |
| FDE extraction/action/fde routes | domain 回退 |
| knowledge_pipeline extractor + extraction_confirm | domain（+ confirm tenant） |
| FDE ontology/k_wave/owl services | domain |
| ontology_case_learning / conversation_ingestor | domain |
| action_bridge / business_event_bridge / action_registry | domain |
| agents / diagnostics / materials_chat / wiki_ontology_engine | domain |
| abstract_goal_decomposer / experience_vector / graph_consensus | domain |
| domain_assessor / retrieval_crag | domain |

## 明确未做

- `workspace_id` / `view_name` / `ProfileConfig(name="default")` 字面量
- `AIPLAT_DEFAULT_TENANT` 运维 env
- N09 / 附录 N 全量认证（certified 仍 false）
