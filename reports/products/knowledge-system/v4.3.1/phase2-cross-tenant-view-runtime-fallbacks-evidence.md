---
doc_type: Report
title: Phase 2 — view_name 运行时回退 SSOT（N09 Batch K64）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / view_name runtime fallbacks（Batch K64）证据

> 实施权威：附录 N N09 partial 加深（`PLATFORM_DEFAULT_VIEW` + `default_view_name()`；CrossDomainResolver / K-wave arbit 运行时 `view_name or "default"` → SSOT；同文件 mop `_ticket_tenant_id` → `default_tenant()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_view_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_view_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_view_runtime_fallbacks_k64.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter | `PLATFORM_DEFAULT_VIEW` + `default_view_name()` |
| knowledge_pipeline/resolver | view_name 回退 |
| FDE k_wave_arbit | view_name + ticket tenant 回退 |

## 明确未做

- `workspace_id` named_workspace 字面量 / `ProfileConfig(name="default")`
- `AIPLAT_DEFAULT_TENANT` 运维 env → SSOT 对齐
- N09 / 附录 N 全量认证（certified 仍 false）
