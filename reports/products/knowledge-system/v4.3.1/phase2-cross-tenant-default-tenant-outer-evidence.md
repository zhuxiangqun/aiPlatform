---
doc_type: Report
title: Phase 2 — default tenant 外层签名默认 SSOT（N09 Batch K50）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / default tenant outer signature defaults（Batch K50）证据

> 实施权威：附录 N N09 partial 加深（facade / syscalls / memory / ontology_engine / platform 等 `tenant_id: str = "default"` → `DomainRouter.default_tenant()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_default_tenant_helper_stable` |
| 目标文件用 SSOT | pass | `test_targets_use_default_tenant_ssot` |
| 生产签名默认清零 | pass | `test_production_tenant_signature_defaults_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_default_tenant_outer_k50.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| CoreFacade / routers / syscalls / memory / ontology_engine | `DomainRouter.default_tenant()` |
| platform delivery / kb / routes / messaging | `from core.api.core_facade import DomainRouter` |

## 明确未做

- SQL 字面量 `tenant_id='default'` → 见 Batch K51
- `or "default"` 回落在 knowledge 以外层（部分仍开放）
- collection_id / session_id `"default"`
- N09 / 附录 N 全量认证（certified 仍 false）
