---
doc_type: Report
title: Phase 2 — Fact/Query wiki_engine.search_pages 热路径加深证据（N19）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 wiki_engine.search_pages 审计热路径证据

> 实施权威：附录 N N19 partial 加深（引擎 `search_pages` **opt-in** 落 Query 快照）。  
> **未宣称** N19 certified / 全部调用点强制落盘（默认关，防内部扫描刷库）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `tenant_id` + `record_hotpath_audit=True` → 落盘 | pass | channel=`wiki_engine_search_pages` |
| 默认 `record_hotpath_audit=False` | pass | 内部调用不审计 |
| suite `wiki_engine_search_pages_hotpath_entry` | pass | `run_fact_query_audit_suite` |
| 行为测默认跳过 / opt-in 落盘 | pass | `test_wiki_engine_search_pages_opt_in_hotpath` |
| list 主返回类型不变 | pass | 仍 `List[Dict]` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| 引擎 | `search_pages(..., tenant_id=, record_hotpath_audit=True)` |
| Facade | 仍走 `wiki_search_pages` 自有审计（勿双开引擎开关） |
| 审计 | `maybe_record_bare_list_hotpath` channel=`wiki_engine_search_pages` |

## 明确未做

- 全部内部 `search_pages` 调用点强制 `record_hotpath_audit=True`
- TripleStore 按 tenant 隔离
- 全部旁路 / N19 certified
