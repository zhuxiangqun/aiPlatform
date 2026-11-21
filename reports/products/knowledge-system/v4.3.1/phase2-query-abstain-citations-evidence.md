---
doc_type: Report
title: Phase 2 — 查询 abstain+citations 防假绿证据（N21 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N21 查询 abstain+citations 证据

> 实施权威：附录 N N21 deepen（防假绿）。  
> **未宣称** N21 certified / cache_hit 全量捷径强制 / list API 改写 / N13 准确率达标。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| abstain 清 citations | pass | suite `abstain_clears_citations` |
| abstain 清 answer | pass | suite `abstain_clears_answer` |
| 无引用命中降级 abstain | pass | suite `hit_requires_citations` |
| Fact Gateway 路径 | pass | suite `fact_gateway_path` |
| object_set 路径 | pass | suite `object_set_path` |
| Wiki 查询形入口 | pass | suite `wiki_path` |
| KB 查询形入口 | pass | suite `kb_path` |
| MaterialsChat RAG 出口 | pass | suite `materials_path` |
| MaterialsChat 非 RAG 捷径 | pass | suite `materials_shortcut_path` |
| GraphRAG 信封 | pass | suite `graphrag_path` |
| wiki_kb_query_entry | pass | suite / gate |
| materials_graphrag_entry | pass | suite / gate |
| materials_shortcut_entry | pass | suite / gate |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_query_abstain_citations_phase2.py -v
# 预期：10 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | validate/enforce + pack + wiki/kb + `enforce_materials_chat_output` + `enforce_materials_chat_shortcut_output` + `attach_graphrag_n21_envelope` |
| 生产 | MaterialsChat RAG 出口；time/math/greeting/thanks 捷径；`GraphRAGRetriever.retrieve` 信封 |
| Facade / HTTP | `/fde/query-abstain-citations*`（含 `/materials` `/materials-shortcut` `/graphrag`） |

## 明确未做

- MaterialsChat cache_hit 等其它非 trivial 捷径强制 enforce
- 改写 `sys_wiki_retrieve` / `sys_kb_retrieve` list 返回形
- 并入 N13 校准准确率宣称
- N21 certified / 关闭 ADR 例外冒充签字
