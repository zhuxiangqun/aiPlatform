---
doc_type: Report
title: Phase 2 — default session SSOT（N09 Batch K53）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / default session SSOT（Batch K53）证据

> 实施权威：附录 N N09 partial 加深（`session_id: str = "default"` → `DomainRouter.default_session()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| PLATFORM_DEFAULT_SESSION + helper | pass | `test_platform_default_session_helper` |
| 目标文件用 SSOT | pass | `test_targets_use_default_session_ssot` |
| 生产签名默认清零 | pass | `test_production_session_signature_defaults_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_default_session_ssot_k53.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter SSOT | `PLATFORM_DEFAULT_SESSION` + `default_session()` |
| kernel / syscall / FDE voice | `session_id: str = DomainRouter.default_session()` |

## 明确未做

- N09 / 附录 N 全量认证（certified 仍 false）
- 非 `session_id` 的其它 `"default"` 业务字符串（若仍有）
