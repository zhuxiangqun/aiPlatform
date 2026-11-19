---
doc_type: Report
title: Phase 2 — platform FDE API GraphIndex 租户证据（N09 Batch K31）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / platform FDE API tenant（Batch K31）证据

> 实施权威：附录 N N09 partial 加深（platform FDE API 第一波）。  
> **未宣称** fde.py / sessions_v2 / diagnostics_v2 / bootstrap / validate / manuals 等后续波次 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `fde_graph_tenant` helper | pass | `test_fde_graph_tenant_prefers_request` |
| wave1 8 文件无 bare load | pass | `test_k31_wave_sources_wire_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_platform_fde_api_tenant_k31.py -v
# 预期：2 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| `apps/fde/api/graph_tenant.py` | `resolve_request_tenant(request)` → `_resolve_graph_tenant()` |
| action_routes / ask / delivery / dashboard / trends / sessions_compare / governance / rapid_insight | `GraphIndex.load(..., tenant_id=fde_graph_tenant())` |

## 明确未做

- wave2 文件 → 见 Batch K32；域名硬编码仍残余
- custom_handlers / scripts seed 工具面
- N09 / 附录 N 全量认证
