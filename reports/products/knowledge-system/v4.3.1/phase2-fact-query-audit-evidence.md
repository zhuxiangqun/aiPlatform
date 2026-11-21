---
doc_type: Report
title: Phase 2 — Fact/Query 统一审计快照证据（N19 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 Fact/Query 统一审计证据

> 实施权威：附录 N N19 deepen（运行时权威与审计快照统一 + put_fact/Gateway/query_facts/MaterialsChat/GraphRAG/Wiki-KB/裸 list/KB Q&A·CRAG/统一 knowledge_retrieve/`sys_wiki_context` 热路径）。  
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
| KB Q&A / CRAG 旁路 | pass | suite `kb_qa_hotpath_entry` |
| 统一 knowledge_retrieve 旁路 | pass | suite `knowledge_retrieve_hotpath_entry` |
| Agent wiki_context 旁路 | pass | suite `wiki_context_hotpath_entry` + `phase2-fact-query-wiki-context-hotpath-evidence.md` |
| Wiki 结构化查询旁路 | pass | suite `wiki_structured_hotpath_entry` + `phase2-fact-query-wiki-structured-hotpath-evidence.md` |
| Agent ontology_context 旁路 | pass | suite `ontology_context_hotpath_entry` + `phase2-fact-query-ontology-context-hotpath-evidence.md` |
| URN ontology syscall/HTTP 旁路 | pass | suite `ontology_urn_hotpath_entry` + `phase2-fact-query-ontology-urn-hotpath-evidence.md` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：exit 0（含 wiki_context 门）
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `record_audit_snapshot` / `maybe_record_*_hotpath` / suite/gate |
| 热路径 | `put_fact` + `unified_query_gateway` + `query_facts_gateway` + `query_facts` list + MaterialsChat `_n21_enforce_*` + GraphRAG `attach_graphrag_n21_envelope` + Wiki/KB `attach_list_retrieve_n21_envelope` / `query_*_with_abstain` + 裸 `sys_wiki_retrieve`/`sys_kb_retrieve` + `sys_crag_retrieve`/`kb_qa_retrieve` + `sys_knowledge_retrieve` + Agent `sys_wiki_context`（信封失败兜底）+ `wiki_structured_query_api` + Agent `sys_ontology_context`（域）+ URN `syscalls/ontology.py` + HTTP `ontology_routes` → best-effort（`AIPLAT_FACT_QUERY_AUDIT_HOTPATH`） |
| Facade / HTTP | 同名 + `/fde/fact-query-audit*` |
| 配置 | `AIPLAT_FACT_QUERY_AUDIT_DB` / `AIPLAT_FACT_QUERY_AUDIT_HOTPATH` |

## 明确未做

- 全部旁路入口强制落盘（残余其它 Agent/评测直连等）
- 热路径失败阻断主写入/查询（刻意 best-effort）
- Package+Action 统一审计总线全量合并（N24）
- N19 certified / 关闭 ADR 例外冒充签字

> wiki_context 加深见 `phase2-fact-query-wiki-context-hotpath-evidence.md`。
