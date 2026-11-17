---
doc_type: Report
title: Phase 2 — GraphIndex 图层跨租户证据（N09 Batch K5）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / GraphIndex 图层租户（Batch K5）证据

> 实施权威：附录 N N09 partial 加深（K4 caller 透传之上接线 GraphRAG→GraphIndex）。  
> **未宣称** 全量图写入路径强制 tenant / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 既有十探针仍 pass | pass | `run_cross_tenant_isolation_suite` |
| GraphIndex 跨租户找不到节点 | pass | `graphindex_no_leak` |
| GraphRAG 图层透传 tenant | pass | `_find_node` / `_extract_subgraph` / keyword 回退 |
| certified 恒 false | pass | gate / honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed（suite 11/11）
```

## 接线

| 入口 | 路径 |
|------|------|
| Harden | `GraphRAGRetriever._find_node/_extract_subgraph/_extract_query_entities(tenant_id=)` → `GraphIndex.load(domain, tenant_id=)` |
| 套件 | 临时 `AIPLAT_HOME` + per-tenant `{tenant}:{domain}.db` |
| Facade | 既有套件入口（无签名变） |

## 明确未做

- 全量图写入/投影路径强制 tenant 校验（extract→GraphIndex 写路径见 Batch K6：`phase2-cross-tenant-graph-write-evidence.md`）
- N09 / 附录 N 全量认证
