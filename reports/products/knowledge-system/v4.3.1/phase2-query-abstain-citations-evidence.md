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
> **未宣称** N21 certified / Wiki·KB·GraphRAG 全入口热路径强制 / N13 准确率达标。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| abstain 清 citations | pass | suite `abstain_clears_citations` |
| abstain 清 answer | pass | suite `abstain_clears_answer` |
| 无引用命中降级 abstain | pass | suite `hit_requires_citations` |
| Fact Gateway 路径 | pass | suite `fact_gateway_path` |
| object_set 路径 | pass | suite `object_set_path` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_query_abstain_citations_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `validate_abstain_citations` / `enforce_abstain_citations` / suite/gate |
| Facade / HTTP | 同名 + `/fde/query-abstain-citations*` |

## 明确未做

- Wiki / KB / GraphRAG 全入口热路径强制 enforce
- 并入 N13 校准准确率宣称
- N21 certified / 关闭 ADR 例外冒充签字
