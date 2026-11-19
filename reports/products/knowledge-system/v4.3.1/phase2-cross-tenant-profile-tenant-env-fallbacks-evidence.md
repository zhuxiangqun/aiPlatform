---
doc_type: Report
title: Phase 2 — profile + AIPLAT_DEFAULT_TENANT 运行时回退 SSOT（N09 Batch K66）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / profile + tenant-env runtime fallbacks（Batch K66）证据

> 实施权威：附录 N N09 partial 加深（ProfileConfig/kanban/cron/inference/diagnostics/judge 运行时 profile `"default"` → `DomainRouter.default_profile()`；`AIPLAT_DEFAULT_TENANT` 缺省字面量 → `default_tenant()`，env 仍可覆盖）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_profile_tenant_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_profile_tenant_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_profile_tenant_env_fallbacks_k66.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| kernel ProfileManager.get_default | name→`default_profile()`；namespace→`default_session()` |
| cron_loader / inference /profile | `default_profile()` |
| kanban Query / diagnostics switch_profile | `default_profile()` |
| judge_v1 tag fallback | `default_profile()` |
| platform TenantManager | `AIPLAT_DEFAULT_TENANT` or `default_tenant()` |

## 明确未做

- N09 / 附录 N 全量认证（certified 仍 false）
- 其它非隔离语义的 `"default"` 字面量（如业务 tag / 状态枚举）
