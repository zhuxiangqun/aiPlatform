---
doc_type: Report
title: Phase 2 — Fact/Query 统一审计快照证据（N19 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N19 Fact/Query 统一审计证据

> 实施权威：附录 N N19 deepen（运行时权威与审计快照统一）。  
> **未宣称** N19 certified / put_fact·query_gateway 热路径强制落快照 / N24 全量总线合并。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Fact 快照写入 | pass | suite `fact_snapshot_written` |
| Query 快照写入 | pass | suite `query_snapshot_written` |
| 统一 schema | pass | suite `unified_schema` |
| 租户隔离列表 | pass | suite `tenant_scoped_list` |
| runtime_authority | pass | suite `runtime_authority_flag` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `record_audit_snapshot` / `list_audit_snapshots` / suite/gate |
| Facade / HTTP | 同名 + `/fde/fact-query-audit*` |
| 配置 | `AIPLAT_FACT_QUERY_AUDIT_DB` |

## 明确未做

- 强制全部 put_fact / query_gateway 热路径自动落快照
- Package+Action 统一审计总线全量合并（N24）
- N19 certified / 关闭 ADR 例外冒充签字
