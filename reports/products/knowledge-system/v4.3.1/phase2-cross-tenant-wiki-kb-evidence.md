---
doc_type: Report
title: Phase 2 — 跨租户 Wiki/KB 加深证据（N09 Batch K2）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / 跨租户 Wiki + KB（Batch K2）证据

> 实施权威：附录 N N09 partial 加深（K1 六探针之上扩 Wiki/KB 入口）。  
> **未宣称** 全域 0 泄漏认证 / N09 certified / GraphRAG 全入口。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 既有六探针仍 pass | pass | `run_cross_tenant_isolation_suite` |
| KB 跨租户空 | pass | `kb_retrieve_no_leak`（per-tenant sqlite 路径） |
| Wiki mismatch→空 | pass | `wiki_retrieve_no_leak`（retriever/query tenant 硬门） |
| certified 恒 false | pass | gate / honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed（suite 8/8）
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `run_cross_tenant_isolation_suite` 增 2 探针 |
| KB | 临时 `AIPLAT_KB_TENANTS_DIR` + `sys_kb_retrieve` |
| Wiki | `WikiPageRetriever(tenant_id=A)` + `KnowledgeQuery(tenant_id=B)` → `[]` |
| Facade | 既有 `fact_ledger_run_cross_tenant_suite`（无签名变） |

## 明确未做

- Wiki collection 级跨读 ACL / GraphRAG 全入口跨租户认证（GraphRAG 向量层见 Batch K3：`phase2-cross-tenant-graphrag-evidence.md`）
- N09 / 附录 N 全量认证
