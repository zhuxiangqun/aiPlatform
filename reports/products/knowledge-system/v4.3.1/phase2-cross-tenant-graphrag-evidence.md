---
doc_type: Report
title: Phase 2 — 跨租户 GraphRAG 加深证据（N09 Batch K3）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / 跨租户 GraphRAG（Batch K3）证据

> 实施权威：附录 N N09 partial 加深（K2 八探针之上扩 GraphRAG 向量层）。  
> **未宣称** 全域 0 泄漏认证 / N09 certified / GraphIndex 图节点租户隔离。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 既有八探针仍 pass | pass | `run_cross_tenant_isolation_suite` |
| GraphRAG 向量层跨租户空 | pass | `graphrag_no_leak` |
| 显式 tenant 不回退 default/wiki | pass | `GraphRAGRetriever._vector_search(tenant_id=)` |
| certified 恒 false | pass | gate / honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed（suite 9/9）
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `run_cross_tenant_isolation_suite` 增 `graphrag_no_leak` |
| Harden | `GraphRAGRetriever.retrieve` / `_vector_search` 增 `tenant_id`；非空时只查该租户且禁 wiki/default 回退 |
| Facade | 既有 `fact_ledger_run_cross_tenant_suite`（无签名变） |

## 明确未做

- GraphIndex 图节点级租户隔离（CRAG/治理透传见 Batch K4：`phase2-cross-tenant-graphrag-caller-evidence.md`）
- N09 / 附录 N 全量认证
