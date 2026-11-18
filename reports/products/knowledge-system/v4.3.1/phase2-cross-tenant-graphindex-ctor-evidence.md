---
doc_type: Report
title: Phase 2 — GraphIndex 直构 / branch DB 租户证据（N09 Batch K34）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / GraphIndex ctor · branch tenant（Batch K34）证据

> 实施权威：附录 N N09 partial 加深（`GraphIndex(...)` 直构 + ontology branch DB 前缀 + FDE API 透传）。  
> **未宣称** 域名硬编码消除 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 目标文件无裸 `GraphIndex(` | pass | `test_k34_targets_no_bare_graphindex_ctors` |
| branch DB 租户前缀 | pass | `test_branch_db_path_tenant_prefix` |
| branch resolve 显式优先 | pass | `test_branch_resolve_prefers_explicit` |
| FDE API fork/diff/merge/export 透传 | pass | `test_fde_api_branch_okf_pass_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_graphindex_ctor_tenant_k34.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| ontology_branch | `_branch_db_path(..., tenant_id)` + `GraphIndex(..., tenant_id=tid)` |
| okf_exporter | `GraphIndex.load(..., tenant_id=)`（替换坏掉的 instance `load(load_nodes=True)`） |
| graph_importer / recon / retrieval / validator / wiki / hallucination / doc_quality | ctor + `_resolve_graph_tenant` |
| FDE API | `tenant_id=fde_graph_tenant()` → fork/diff/merge/delete/export-okf |

## 明确未做

- scripts 侧 `GraphIndex(` — 已由 K35 覆盖（见 `phase2-cross-tenant-scripts-ctor-evidence.md`）
- FDE/平台业务域名硬编码消除
- N09 / 附录 N 全量认证（certified 仍 false）
