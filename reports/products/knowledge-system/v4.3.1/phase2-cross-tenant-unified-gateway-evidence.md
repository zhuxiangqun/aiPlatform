---
doc_type: Report
title: Phase 2 — 跨租户统一 Gateway 探针证据（N09 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / 跨租户统一 Gateway（N09 deepen）证据

> 实施权威：附录 N N09 partial 加深（接 N06 统一入口）。  
> **未宣称** 全域 0 泄漏 / N09 certified；仅把 `unified_query_gateway`
> 的 fact/object_set 路由纳入跨租户套件必选探针。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| unified fact 路由跨租户 abstain | pass | suite `unified_gateway_fact_no_leak` |
| unified object_set 路由跨租户无 citation | pass | suite `unified_gateway_object_set_no_leak` |
| 套件 15 探针全绿 + certified 恒 false | pass | `test_suite_passes_and_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed（suite passed==15）
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `run_cross_tenant_isolation_suite`（新增 2 探针） |
| 依赖 | `unified_query_gateway(..., bindings_path=)` 透传 object_set 探针 |

## 明确未做

- 全域入口 0 泄漏认证 / 无等级 mop 恢复为 Core 条件
- N09 certified / 关闭 ADR 例外
