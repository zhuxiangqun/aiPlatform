---
doc_type: Report
title: Phase 2 — Fact/Query wiki_structured 热路径加深证据（N19）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 wiki_structured 审计热路径证据

> 实施权威：附录 N N19 partial 加深（Wiki 结构化查询 Facade/HTTP 旁路落 Query 快照）。  
> **未宣称** N19 certified / 全部旁路强制。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Facade `wiki_structured_query_api` 热路径 | pass | `core_facade.py` → `maybe_record_wiki_kb_hotpath(channel=wiki_structured)` |
| HTTP `tenant_id`/`domain_id` 透传 | pass | `wiki.py` `/query-structured` |
| suite `wiki_structured_hotpath_entry` | pass | `run_fact_query_audit_suite` |
| 行为测有 tenant 落盘 / 空 tenant 跳过 | pass | `test_wiki_structured_query_api_hotpath` |
| certified 恒 false | pass | Facade 回执 + suite/gate |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| HTTP | `GET /api/.../wiki/query-structured?q=&tenant_id=` |
| Facade | `wiki_structured_query_api` |
| 审计 | `maybe_record_wiki_kb_hotpath` channel=`wiki_structured` |

## 明确未做

- 无 tenant 的内部 golden 回归调用强制落盘
- 全部旁路 / N19 certified
