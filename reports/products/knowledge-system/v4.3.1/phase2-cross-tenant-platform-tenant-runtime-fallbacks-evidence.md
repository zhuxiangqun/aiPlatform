---
doc_type: Report
title: Phase 2 — platform routes/kb/delivery tenant 运行时回退 SSOT（N09 Batch K56）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / platform tenant runtime fallbacks（Batch K56）证据

> 实施权威：附录 N N09 partial 加深（platform routes / kb / delivery 运行时 `tenant_id or "default"` → `DomainRouter.default_tenant()`）。  
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
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_platform_tenant_runtime_fallbacks_k56.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| `api/rest/routes.py` | identity / vault / batches → `DomainRouter.default_tenant()` |
| onboarding / conversations / approvals | actor/request tenant 回退 |
| `kb/storage.py` / `kb/platform_query.py` | strip-or / query tenant+collection |
| delivery kb_health / monthly_ops / l3 / cost | 报表 tenant 字段 |

## 明确未做

- apps/org / value / prompt / fde rapid_insight 等其它 `body.get("tenant_id", "default")` → 见 K57
- core `ontology_branch` `(tenant_id or "default").strip()` 残留 → 见 K57
- N09 / 附录 N 全量认证（certified 仍 false）
