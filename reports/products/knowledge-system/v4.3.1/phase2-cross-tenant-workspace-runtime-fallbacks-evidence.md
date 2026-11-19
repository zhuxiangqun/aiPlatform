---
doc_type: Report
title: Phase 2 — workspace_id 运行时回退 SSOT（N09 Batch K65）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / workspace_id runtime fallbacks（Batch K65）证据

> 实施权威：附录 N N09 partial 加深（`PLATFORM_DEFAULT_WORKSPACE` + `default_workspace_id()`；named_workspace registry/resolve + eval external targets 运行时 `"default"` → SSOT）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_workspace_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_workspace_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_workspace_runtime_fallbacks_k65.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter | `PLATFORM_DEFAULT_WORKSPACE` + `default_workspace_id()` |
| named_workspace/registry | default entry / 创建门 / 路径 |
| named_workspace/resolve | 缺省 workspace_id 回退 |
| eval external_exam_ops / external_targets | workspace 回退 |

## 明确未做

- `ProfileConfig(name="default")` / cron `profile="default"` / inference profile 字面量
- `AIPLAT_DEFAULT_TENANT` 运维 env → SSOT 对齐
- N09 / 附录 N 全量认证（certified 仍 false）
