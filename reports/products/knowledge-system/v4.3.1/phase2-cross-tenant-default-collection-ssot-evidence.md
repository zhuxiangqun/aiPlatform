---
doc_type: Report
title: Phase 2 — default collection/profile SSOT（N09 Batch K52）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / default collection + profile SSOT（Batch K52）证据

> 实施权威：附录 N N09 partial 加深（`collection_id` / `profile_id` 签名默认 / 赋值 / DDL → `DomainRouter.default_collection()` / `default_profile()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| PLATFORM_* + helpers | pass | `test_platform_collection_profile_helpers` |
| 目标文件用 SSOT | pass | `test_targets_use_collection_or_profile_ssot` |
| 生产默认清零 | pass | `test_production_collection_profile_defaults_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_default_collection_ssot_k52.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter SSOT | `PLATFORM_DEFAULT_COLLECTION` / `PLATFORM_DEFAULT_PROFILE` + helpers |
| facade / knowledge / platform KB | 签名默认与 DDL |

## 明确未做

- `session_id = "default"` → 见 Batch K53
- N09 / 附录 N 全量认证（certified 仍 false）
