---
doc_type: Report
title: Phase 2 — Fact/Query 裸 wiki_search_pages 热路径加深证据（N19）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 裸 wiki_search_pages 审计热路径证据

> 实施权威：附录 N N19 partial 加深（Facade 裸 list `wiki_search_pages` 落 Query 快照；信封关下层防双写）。  
> **未宣称** N19 certified / 全部旁路强制 / 改写 list 主返回类型。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 显式 `tenant_id` → `maybe_record_bare_list_hotpath` | pass | channel=`wiki_search_pages` |
| `wiki_search_pages_api` 关下层审计 | pass | `record_hotpath_audit=False` |
| suite `wiki_search_pages_bare_hotpath_entry` | pass | `run_fact_query_audit_suite` |
| 行为测有 tenant 落盘 / 空跳过 / 信封不双写 | pass | `test_wiki_search_pages_bare_hotpath` |
| list 主返回类型不变 | pass | 仍返回 `List[Dict]` |
| certified 恒 false（信封路径） | pass | `wiki_search_pages_api` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Facade 裸 list | `wiki_search_pages(tenant_id=, record_hotpath_audit=True)` |
| 信封 | `wiki_search_pages_api` → 关下层 + channel=`wiki_pages` |
| 审计 | `maybe_record_bare_list_hotpath` channel=`wiki_search_pages` |

## 明确未做

- 引擎层 `wiki_engine.search_pages` 全调用点强制落盘
- FDE 澄清路径自动注入 tenant（仍可选显式）
- 全部旁路 / N19 certified
