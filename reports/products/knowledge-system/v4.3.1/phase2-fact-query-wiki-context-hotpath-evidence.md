---
doc_type: Report
title: Phase 2 — Fact/Query wiki_context 热路径加深证据（N19）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 wiki_context 审计热路径证据

> 实施权威：附录 N N19 partial 加深（Agent `sys_wiki_context`：n21 信封失败时兜底落 Query 快照）。  
> **未宣称** N19 certified / 全部旁路强制。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 信封失败 → `maybe_record_wiki_kb_hotpath` | pass | `wiki_context.py` |
| suite `wiki_context_hotpath_entry` | pass | `run_fact_query_audit_suite` |
| 行为测：信封 raise 仍写快照 | pass | `test_wiki_context_n21_fail_falls_back_to_audit` |
| certified 恒 false | pass | suite / gate |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Agent | `sys_wiki_context` → n21 信封 / N19 兜底 |
| Suite | `wiki_context_hotpath_entry` |

## 明确未做

- 全部 Agent/检索旁路强制落盘
- N19 / 附录 N 全量认证
