---
doc_type: Report
title: Phase 2 — 跨租户隔离加深证据（N09 Batch E3）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / 跨租户隔离（Batch E3）证据

> 实施权威：附录 N N09 partial 加深。  
> **未宣称** 全域 0 泄漏认证 / N09 certified；仅 FactLedger 四探针套件。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| query_facts 跨租户无泄漏 | pass | suite `query_facts_no_leak` |
| get_source 跨租户 None | pass | suite `get_source_no_leak` |
| gateway 跨租户 abstain | pass | suite `gateway_no_leak` |
| verify_raw 跨租户拒绝 | pass | suite `verify_raw_no_leak` |
| certified 恒 false | pass | gate / honesty 断言 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed
```

实测（2026-11-16）：`2 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `run_cross_tenant_isolation_suite` / `evaluate_cross_tenant_gate` |
| Facade | `fact_ledger_run_cross_tenant_suite` + `evaluate_fact_cross_tenant_gate` |

## 明确未做

- Wiki/KB/GraphRAG 全入口跨租户认证
- N09 / 附录 N 全量认证

> ObjectSet + Unified Audit 探针见 Batch K1：`phase2-cross-tenant-objectset-audit-evidence.md`。
