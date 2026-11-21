---
doc_type: Report
title: Phase 2 — Unified Audit Fact/Query 总线热路径证据（N24 Batch J11）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / Unified Audit FactQuery Bus Hotpath（Batch J11）证据

> 实施权威：附录 N N24 partial 加深（`record_audit_snapshot` → `append_unified_audit_event`）。  
> **未宣称** N24 certified / 关闭 ADR 例外。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Fact/Query 写入入 bus | pass | suite `fact_query_hotpath_to_bus` + `test_fact_query_hotpath_to_bus` |
| event_id 与 J10 对齐 | pass | `fqa:{snapshot_id}` 幂等 |
| env 可关总线热路径 | pass | `AIPLAT_FACT_QUERY_AUDIT_BUS_HOTPATH=0` |
| suite/gate certified 恒 false | pass | honesty 测 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_bus_phase2.py -v
# 预期：10 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 写路径 | `record_audit_snapshot` → `_maybe_append_fact_query_to_bus` |
| 配置 | `AIPLAT_FACT_QUERY_AUDIT_BUS_HOTPATH`（默认开） |
| 幂等 | 与 J10 materialize 同 `event_id` |

## 明确未做

- N24 / 附录 N 全量认证
- 改写历史总线行或 N19 快照表
