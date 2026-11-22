---
doc_type: Report
title: Phase 2 — Operational 校准流水线证据（N13 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N13 Operational 校准流水线证据

> 实施权威：附录 N N13 / 附录 O partial 加深。  
> **未宣称** 真实 ECE 训练 / 准确率达标 / N13 certified；仅查询路径封顶 + 流水线套件。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 失败校准 → gateway high 封顶 medium | pass | suite `failed_cal_caps_gateway_high` |
| 达标校准 → 允许 high | pass | suite `approved_cal_allows_high` |
| 缺失校准 → high 封顶 medium | pass | suite `missing_cal_caps_high` |
| suite/gate certified 恒 false | pass | `honesty_certified_false` / `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_calibration_pipeline_phase2.py -v
# 预期：5 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `apply_calibration_ceiling` / `run_calibration_pipeline_suite` / `evaluate_calibration_pipeline_gate` |
| 查询 | `FactLedger.query_facts_gateway`（`domain_id` 非空时封顶） |
| Facade | `run_calibration_pipeline_suite` / `evaluate_calibration_pipeline_gate` |

## 明确未做

- 真实 ECE/Brier 训练流水线 / 准确率宣称
- 全知识域 gold 评测（见 N10）
- N13 certified / 关闭 ADR 例外
