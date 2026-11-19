---
doc_type: Report
title: Phase 2 — 杂项 label 默认 SSOT（N09 Batch K69）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / misc label defaults（Batch K69）证据

> 实施权威：附录 N N09 partial 加深（`PLATFORM_DEFAULT_LABEL` + `default_label()`；gateway `channel` / memory `agent_type` / learning `benchmark_name` / builder `output_style` → SSOT）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_label_ssot` |
| 目标无字面量默认 | pass | `test_target_misc_label_defaults_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_misc_label_defaults_k69.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter | `PLATFORM_DEFAULT_LABEL` + `default_label()` |
| schemas_gateway | `channel` |
| execution_store session_mixin | `agent_type` |
| learning manager | `benchmark_name` |
| schemas_builder | `output_style` |

## 明确未做

- `get_default_model(purpose="default")`（模型 purpose 分类键，非隔离 label）
- N09 / 附录 N 全量认证（certified 仍 false）
