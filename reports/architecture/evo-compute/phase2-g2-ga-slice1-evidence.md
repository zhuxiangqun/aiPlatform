---
doc_type: Report
title: Phase 2 / G2 — 离散 GA 最小切片（slice-1）
status: active
authority: supporting
language: zh-CN
created: 2026-11-25
---
# Phase 2 / G2 discrete GA slice-1

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 2 / Gate G2。  
> 前置：G0 签批 + G1 DE/ES + 三试点电池已合入。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| 离散 GA 算子 | pass | `ga.py`：init / crossover / mutate / `run_ga_offline`（仅 int 字段） |
| 覆盖率探针 | pass | `coverage.py`：评测 ≥90% / FDE ≥95%；缺测 `baseline_missing=true` |
| G2 出口就绪 | pass | `evaluate_g2_exit_readiness`；缺覆盖则 `g2_complete=false` |
| G2 suite / gate | pass | `run_evo_compute_g2_suite`；`g2_complete` 恒 false |
| CoreFacade | pass | `run_evo_ga_offline` / `measure_evo_*_coverage` / `run_evo_compute_g2_suite` |

## 诚实锁

```text
g2_complete=false   # 套件绿 ≠ Gate 宣称完成（缺测覆盖）
certified=false
e2_claimed=false
production_write=false
baseline_missing=true  # 评测/FDE 实测覆盖未接线
```

**未宣称**：评测 L4 ≥90%、FDE 证据 ≥95%、G2/E2 完成、生产写、GP/AIS。  
适应度为确定性代理；覆盖率探针诚实上报缺测。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_g2.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| GA | `core/harness/evo_compute/ga.py` |
| 覆盖率 | `core/harness/evo_compute/coverage.py` |
| 出口就绪 | `core/harness/evo_compute/exit_readiness.py` |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
