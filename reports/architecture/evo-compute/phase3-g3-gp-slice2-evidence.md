---
doc_type: Report
title: Phase 3 / G3 — GP 强类型 DSL 沙箱（slice-2）
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# Phase 3 / G3 GP slice-2

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 3 / Gate G3；算法表见演化架构 §5 GP。  
> 前置：G3 slice-1 AIS 已接线（PR #1069）。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| 强类型 DSL | pass | `ALLOWED_NODE_TYPES` + `validate_dsl_program` |
| 拒核心代码 | pass | 禁止 python/code/exec 等键与源码形态 value |
| 离线 GP | pass | `run_gp_offline`；仅 DSL 内突变/交叉 |
| G3 slice-2 suite / gate | pass | `run_evo_compute_g3_slice2_suite`；`g3_complete` 恒 false |
| CoreFacade | pass | `validate_evo_gp_dsl` / `run_evo_gp_offline` |

## 诚实锁

```text
g3_complete=false
certified=false
e2_claimed=false
dsl_only=true（合法个体）
emits_core_code=false
production_write=false
```

**未宣称**：生产候选 100% HUMAN_GATE、闭环 L4、G3/E2 完成。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_g3_slice2.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| GP DSL | `core/harness/evo_compute/gp.py` |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
