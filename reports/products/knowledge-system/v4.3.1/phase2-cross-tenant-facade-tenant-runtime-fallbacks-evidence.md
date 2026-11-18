---
doc_type: Report
title: Phase 2 — facade/diagnostics tenant 运行时回退 SSOT（N09 Batch K55）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / facade tenant runtime fallbacks（Batch K55）证据

> 实施权威：附录 N N09 partial 加深（`core_facade` + `diagnostics` 运行时 `tenant_id or "default"` → `DomainRouter.default_tenant()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_default_tenant_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_tenant_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_facade_tenant_runtime_fallbacks_k55.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| core_facade auto_ontology / graph / kb / audit 等 | `tid = (...).strip() or DomainRouter.default_tenant()` |
| core_facade 其余 `tenant_id or "default"` | `or DomainRouter.default_tenant()` |
| diagnostics drift / staleness 身份 | `actor0.get("tenant_id") ... or DomainRouter.default_tenant()` |

## 明确未做

- platform routes / kb / delivery 大量 `tenant_id or "default"` → 后续批次
- facade 内 collection/session 字面量回退（已有 K52/K53 签名 SSOT）
- N09 / 附录 N 全量认证（certified 仍 false）
