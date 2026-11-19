---
doc_type: Report
title: Phase 2 — FDE tracking domain 去硬编码证据（N09 Batch K38）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / FDE tracking domain（Batch K38）证据

> 实施权威：附录 N N09 partial 加深（platform FDE API `fde-delivery` → `DomainRouter.tracking_domain()`）。  
> **未宣称** 全域域名硬编码清零 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| platform FDE API 无裸 `fde-delivery` load | pass | `test_platform_fde_api_no_hardcoded_fde_delivery_loads` |
| `fde_graph_domain` → tracking_domain | pass | `test_fde_graph_domain_uses_tracking_domain` |
| 无 harness 直导 | pass | `test_graph_tenant_module_exports_domain_helper` |
| sessions_v2 接线 | pass | `test_sessions_v2_loads_via_fde_graph_domain` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fde_tracking_domain_k38.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| `fde_graph_domain()` | CoreFacade `get_domain_router().tracking_domain()` |
| platform FDE GraphIndex.load / list_branches | `fde_graph_domain()` + `fde_graph_tenant()` |

## 明确未做

- `enterprise-terms` / `knowledge-atom` 等其它域名硬编码 — platform FDE 见 K39；harness 仍延后
- core `apps/fde/service` 内 `fde-delivery` 字面量 — clarify_dialog 见 K39
- DomainRouter.PLATFORM_TRACKING_DOMAIN 常量本身仍为 `fde-delivery`（SSOT，非调用点硬编码）
- N09 / 附录 N 全量认证（certified 仍 false）
