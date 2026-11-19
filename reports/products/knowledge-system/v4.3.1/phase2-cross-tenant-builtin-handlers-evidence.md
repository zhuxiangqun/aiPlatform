---
doc_type: Report
title: Phase 2 — builtin_handlers GraphIndex 租户证据（N09 Batch K27）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / builtin_handlers tenant（Batch K27）证据

> 实施权威：附录 N N09 partial 加深（builtin action handlers GraphIndex）。  
> **未宣称** FDE service bare load / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| builtin_handlers 11 处 load tenant | pass | `test_builtin_handlers_source_wires_tenant` |
| `_graph_tenant` 优先 params | pass | `test_graph_tenant_prefers_params` |
| approve_diagnosis 透传 | pass | `test_approve_diagnosis_loads_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_builtin_handlers_tenant_k27.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| builtin_handlers | `_graph_tenant(params)` → `params.tenant_id` / `_resolve_graph_tenant` → `GraphIndex.load(..., tenant_id=)`（11 处） |

## 明确未做

- FDE service → 见 Batch K28；core_facade / system / eval / infra bare load 仍残余
- N09 / 附录 N 全量认证
