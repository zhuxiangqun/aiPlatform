---
doc_type: Report
title: Phase 2 — Fact/Query ontology_context 热路径加深证据（N19）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 ontology_context 审计热路径证据

> 实施权威：附录 N N19 partial 加深（Agent `sys_ontology_context` 含 search_pages 旁路落 Query 快照）。  
> **未宣称** N19 certified / 全部旁路强制。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `tenant_id` 非空 → `maybe_record_wiki_kb_hotpath` | pass | `ontology_context.py` channel=`ontology_context` |
| pipeline_prompt 透传 `state.tenant_id` | pass | `pipeline_prompt.py` |
| suite `ontology_context_hotpath_entry` | pass | `run_fact_query_audit_suite` |
| 行为测有 tenant 落盘 / 空跳过 | pass | `test_ontology_context_hotpath` |
| certified 恒 false | pass | 回执 + suite/gate |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Agent | `sys_ontology_context(tenant_id=)` |
| Pipeline | `pipeline_prompt` → `state.tenant_id` |
| 审计 | `maybe_record_wiki_kb_hotpath` channel=`ontology_context` |

## 明确未做

- 全部旁路 / N19 certified

> URN 版 syscall + HTTP 加深见 `phase2-fact-query-ontology-urn-hotpath-evidence.md`。
