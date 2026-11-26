---
doc_type: Report
title: Phase 3 / G3 — AIS 异常检测最小切片（slice-1）
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# Phase 3 / G3 AIS slice-1

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 3 / Gate G3；算法表见演化架构 §5 AIS。  
> 前置：G2 slice-1/2/3 已合入。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| 抗体签名 | pass | `default_antibody_signatures`（执行异常/注入/跨租户/知识冲突） |
| 检测器 | pass | `detect_anomalies`；`auto_remediate=false` |
| 误报预算 | pass | 预注册 `false_positive_budget`；超预算诚实上报 |
| G3 suite / gate | pass | `run_evo_compute_g3_suite`；`g3_complete` 恒 false |
| CoreFacade | pass | `detect_evo_ais_anomalies` / `evaluate_evo_g3_exit_readiness` |

## 诚实锁

```text
g3_complete=false
certified=false
e2_claimed=false
auto_remediate=false
production_write=false
```

**未宣称**：GP DSL、生产候选 100% HUMAN_GATE、闭环 L4、G3/E2 完成。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_g3.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| AIS | `core/harness/evo_compute/ais.py` |
| 出口就绪 | `core/harness/evo_compute/exit_readiness.py` |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
