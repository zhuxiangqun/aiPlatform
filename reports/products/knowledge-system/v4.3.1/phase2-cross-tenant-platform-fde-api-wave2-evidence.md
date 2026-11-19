---
doc_type: Report
title: Phase 2 — platform FDE API GraphIndex 租户证据（N09 Batch K32 wave2）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / platform FDE API tenant（Batch K32 wave2）证据

> 实施权威：附录 N N09 partial 加深（platform FDE API 第二波）。  
> **未宣称** 域名硬编码消除 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| wave2 6 文件无 bare load | pass | `test_k32_wave_sources_wire_tenant` |
| apps/fde/api 全量无 bare load | pass | `test_platform_fde_api_no_bare_graphindex_loads` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_platform_fde_api_tenant_k32.py -v
# 预期：2 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| fde.py / sessions_v2 / diagnostics_v2 / bootstrap / validate / manuals | `fde_graph_tenant()` → `GraphIndex.load(..., tenant_id=)` |

## 明确未做

- `fde-delivery` / `enterprise-terms` / `knowledge-atom` 等域名硬编码（仅补 tenant）
- custom_handlers / scripts → 见 Batch K33
- N09 / 附录 N 全量认证
