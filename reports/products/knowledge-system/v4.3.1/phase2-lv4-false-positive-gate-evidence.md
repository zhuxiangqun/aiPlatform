---
doc_type: Report
title: Phase 2 — Lv4 误报门重设计证据（N08 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N08 Lv4 误报门重设计证据

> 实施权威：附录 N N08 deepen（Lv4 误报门 v2）。  
> **未宣称** N08 certified / 全量 Action 已 Lv4 / 关闭 ADR 例外。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 0 样本拒绝 | pass | suite `zero_samples_denied` |
| 高误报拒绝 | pass | suite `high_fp_denied` |
| 无 rollback 拒绝 | pass | suite `missing_rollback_denied` |
| 健康路径允许 | pass | suite `healthy_allowed` |
| redesigned=true | pass | suite / gate |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_lv4_false_positive_gate_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `evaluate_lv4_fp_gate` / suite/gate |
| Registry | `AsyncActionRegistry` 闭环评估委托 v2 |
| Facade / HTTP | `/fde/lv4-false-positive*` |
| 配置 | `AIPLAT_LV4_MIN_SAMPLES`（默认 10） |

## 明确未做

- 宣称全量 Action 已达 Lv4 自动闭环
- 删除 kill switch / require_approval 既有路径
- N08 certified / 关闭 ADR 例外冒充签字
