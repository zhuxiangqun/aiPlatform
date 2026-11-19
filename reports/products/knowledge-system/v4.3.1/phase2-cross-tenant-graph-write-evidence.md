---
doc_type: Report
title: Phase 2 — 图写入路径 tenant 强制证据（N09 Batch K6）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / 图写入 tenant 强制（Batch K6）证据

> 实施权威：附录 N N09 partial 加深（K5 图层读之上强制 extract→GraphIndex 写路径）。  
> **未宣称** 全量 ontology publish/snapshot 写路径 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 既有十一探针仍 pass | pass | `run_cross_tenant_isolation_suite` |
| 缺 tenant 写图被拒 | pass | `graph_write_tenant` → `tenant_id_required` |
| 带 tenant 写入仅本租户可见 | pass | 同上 + `_find_node` 负向 |
| confirm 透传 tenant | pass | `PendingExtractionStore.confirm` / `run_confirm_extraction` |
| certified 恒 false | pass | gate / honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed（suite 12/12）
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `write_extraction_to_graph_index(..., tenant_id=)` 必填；空 → `tenant_id_required` |
| Confirm | extractor.confirm + `run_confirm_extraction` 透传 row/receipt tenant |
| 套件 | `graph_write_tenant` |

## 明确未做

- ontology publish / snapshot / CrossDomainResolver 写边全量 tenant 强制（见 Batch K7：`phase2-cross-tenant-cross-domain-snapshot-evidence.md`）
- N09 / 附录 N 全量认证
