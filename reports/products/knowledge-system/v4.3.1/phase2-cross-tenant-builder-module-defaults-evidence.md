---
doc_type: Report
title: Phase 2 — builder module_id 默认 SSOT（N09 Batch K68）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / builder module_id defaults（Batch K68）证据

> 实施权威：附录 N N09 partial 加深（`PLATFORM_DEFAULT_MODULE` + `default_module_id()`；builder L2–L5 / project_service / schema_migration 的 `module_id="default"` → SSOT）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_module_ssot` |
| 目标无 module_id 字面量 | pass | `test_target_builder_module_defaults_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_builder_module_defaults_k68.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter | `PLATFORM_DEFAULT_MODULE` + `default_module_id()` |
| builder_l2l5_mixin | 签名 / 分支 / 单模块根路径 |
| builder_project_service | rebuild module_id |
| schema_migration | module_id 默认 |

## 明确未做

- `benchmark_name` / `channel` / `agent_type` / `output_style` / `purpose="default"` 等非 module 隔离语义
- N09 / 附录 N 全量认证（certified 仍 false）
