---
doc_type: Report
title: Phase 2 — Fact/Query FDE clarify tenant 热路径加深证据（N19）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 FDE clarify tenant 透传证据

> 实施权威：附录 N N19 partial 加深（FDE `/clarify` → `_get_knowledge_context` → `wiki_search_pages(tenant_id=)`）。  
> **未宣称** N19 certified / 全部旁路强制 / 引擎层 `search_pages` 全量。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `_get_knowledge_context(tenant_id=)` 透传 | pass | `fde.py` |
| `_clarify` 解析 body/extra 或 `fde_graph_tenant` | pass | `fde.py` |
| `/clarify` 顶层 `tenant_id` → extra | pass | `clarify` |
| pipeline 自检透传 | pass | `fde_pipeline.py` |
| suite `fde_clarify_tenant_hotpath_entry` | pass | 源码门 |
| 行为测有 tenant 落盘 / 空跳过 | pass | `test_fde_clarify_knowledge_context_passes_tenant` |
| certified 恒 false | pass | suite/gate |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| HTTP | `POST /fde/clarify` `tenant_id` / `extra.tenant_id` |
| 澄清引擎 | `_clarify` → `_get_knowledge_context(tenant_id=)` |
| 审计 | `wiki_search_pages` → `maybe_record_bare_list_hotpath` |

## 明确未做

- TripleStore 按 tenant 隔离
- 全部旁路 / N19 certified
