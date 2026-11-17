---
doc_type: Report
title: Phase 2 — 跨租户 ObjectSet/UnifiedAudit 加深证据（N09 Batch K1）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / 跨租户 ObjectSet + Unified Audit（Batch K1）证据

> 实施权威：附录 N N09 partial 加深（E3 四探针之上扩 ObjectSet / Unified Audit）。  
> **未宣称** 全域 0 泄漏认证 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 既有四探针仍 pass | pass | `run_cross_tenant_isolation_suite` |
| ObjectSet 跨租户空 | pass | `object_set_no_leak` |
| Unified Audit / ActionStore 跨租户空 | pass | `unified_audit_no_leak` |
| certified 恒 false | pass | gate / honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed（suite 6/6）
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `run_cross_tenant_isolation_suite` 增 2 探针 |
| ObjectSet | 临时 `N09Probe` ObjectType 绑定 + `query_object_set` |
| Unified Audit | `ActionStore.insert_audit` → `list_unified_audit_events(streams=[action_store])` |
| Facade | 既有 `fact_ledger_run_cross_tenant_suite`（无签名变） |

## 明确未做

- Wiki / KB / GraphRAG 全入口跨租户认证（Wiki/KB 探针见 Batch K2：`phase2-cross-tenant-wiki-kb-evidence.md`）
- N09 / 附录 N 全量认证
