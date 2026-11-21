---
doc_type: Report
title: Phase 2 — Fact/Query ontology URN 热路径加深证据（N19）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 ontology URN 审计热路径证据

> 实施权威：附录 N N19 partial 加深（syscall 包导出的 URN 版 `sys_ontology_context` + HTTP `ontology_routes` 落 Query 快照）。  
> **未宣称** N19 certified / 全部旁路强制 / tenant 隔离。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| URN syscall `tenant_id` → `maybe_record_wiki_kb_hotpath` | pass | `ontology.py` channel=`ontology_urn` |
| HTTP `/query` `/impact` 可选 tenant | pass | `ontology_routes.py` channel=`ontology_urn_http` |
| suite `ontology_urn_hotpath_entry` | pass | `run_fact_query_audit_suite` |
| 行为测有 tenant 落盘 / 空跳过 | pass | `test_ontology_urn_hotpath` + `test_ontology_urn_http_hotpath` |
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
| Agent syscall 包 | `from core.harness.syscalls import sys_ontology_context` → `ontology.py` |
| HTTP | `POST /api/core/ontology/query` · `GET /api/core/ontology/impact/...` |
| 审计 | `maybe_record_wiki_kb_hotpath` channel=`ontology_urn` / `ontology_urn_http` |

## 明确未做

- TripleStore 按 tenant 隔离（SECURITY V2）
- 全部旁路 / N19 certified
