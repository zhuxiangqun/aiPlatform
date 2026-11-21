---
doc_type: Report
title: Phase 2 — Fact/Query 统一审计快照证据（N19 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 Fact/Query 统一审计证据

> 实施权威：附录 N N19 deepen（运行时权威与审计快照统一 + put_fact/Gateway/query_facts/MaterialsChat/GraphRAG/Wiki-KB/裸 list syscall 热路径）。  
> **未宣称** N19 certified / 全部旁路入口强制落盘 / N24 全量总线合并。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Fact 快照写入 | pass | suite `fact_snapshot_written` |
| Query 快照写入 | pass | suite `query_snapshot_written` |
| 统一 schema | pass | suite `unified_schema` |
| 租户隔离列表 | pass | suite `tenant_scoped_list` |
| runtime_authority | pass | suite `runtime_authority_flag` |
| 热路径 helper | pass | suite `hotpath_helper_writes` |
| put_fact 热路径入口 | pass | suite `put_fact_hotpath_entry` |
| Gateway 热路径入口 | pass | suite `query_gateway_hotpath_entry` |
| query_facts_gateway 旁路 | pass | suite `query_facts_gateway_hotpath_entry` |
| query_facts list 旁路 | pass | suite `query_facts_list_hotpath_entry` |
| MaterialsChat 直出旁路 | pass | suite `materials_chat_hotpath_entry` |
| GraphRAG 旁路 | pass | suite `graphrag_hotpath_entry` |
| Wiki/KB 旁路 | pass | suite `wiki_kb_hotpath_entry` |
| 裸 list syscall 旁路 | pass | suite `bare_list_hotpath_entry` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：9 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `record_audit_snapshot` / `maybe_record_*_hotpath` / suite/gate |
| 热路径 | `put_fact` + `unified_query_gateway` + `query_facts_gateway` + `query_facts` list + MaterialsChat `_n21_enforce_*` + GraphRAG `attach_graphrag_n21_envelope` + Wiki/KB `attach_list_retrieve_n21_envelope` / `query_*_with_abstain` + 裸 `sys_wiki_retrieve`/`sys_kb_retrieve`（上层信封调用关 `record_hotpath_audit` 防双写；直出与 Gateway 分立）→ best-effort（`AIPLAT_FACT_QUERY_AUDIT_HOTPATH`） |
| Facade / HTTP | 同名 + `/fde/fact-query-audit*` |
| 配置 | `AIPLAT_FACT_QUERY_AUDIT_DB` / `AIPLAT_FACT_QUERY_AUDIT_HOTPATH` |

## 明确未做

- 全部旁路入口强制落盘（其它 Agent / Workbench 查询形等）
- 热路径失败阻断主写入/查询（刻意 best-effort）
- Package+Action 统一审计总线全量合并（N24）
- N19 certified / 关闭 ADR 例外冒充签字
