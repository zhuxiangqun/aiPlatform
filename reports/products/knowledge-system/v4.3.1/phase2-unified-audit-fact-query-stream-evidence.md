---
doc_type: Report
title: Phase 2 — Unified Audit Fact/Query 源流证据（N24 Batch J10）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / Unified Audit FactQuery Stream（Batch J10）证据

> 实施权威：附录 N N24 partial 加深（N19 Fact/Query 审计快照 fan-in 统一视图 + materialize）。  
> **未宣称** N24 certified / 关闭 ADR 例外。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| view 默认含 `fact_query_audit` | pass | suite `fact_query_audit_stream_present` |
| materialize 吞入 FactQuery | pass | suite `materialize_source_streams` 含 `fact_query_audit` |
| 跨租户不泄漏 | pass | suite `cross_tenant_empty` |
| suite/gate certified 恒 false | pass | honesty 测 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_view_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_bus_phase2.py -v
# 预期：13 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| View | `_fact_query_audit_events` ← `list_audit_snapshots` |
| Materialize | 默认源流含 `fact_query_audit` |
| HTTP | `/unified-audit` streams=`fact_query_audit` |
| 配置 | `AIPLAT_FACT_QUERY_AUDIT_DB` / `AIPLAT_UNIFIED_AUDIT_STREAMS` |

## 明确未做

- N24 / 附录 N 全量认证
- 改写 N19 快照表或 ActionStore 历史
- 热路径双写总线（仍只读汇合 + materialize）
