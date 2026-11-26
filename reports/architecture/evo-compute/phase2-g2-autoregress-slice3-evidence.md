---
doc_type: Report
title: Phase 2 / G2 — 自动回归门（slice-3）
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# Phase 2 / G2 auto-regression slice-3

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 2 / Gate G2；数据集隔离见演化架构 §10.1。  
> 前置：G2 slice-1（GA）+ slice-2（覆盖实测路径）已合入。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| 冻结回归集 | pass | `default_regression_set` = replay.regression + 对抗样本；版本 `regression_fixture_v1` |
| 自动回归门 | pass | `run_regression_gate`：质量塌陷/失败数/安全变差拒收 |
| 隔离诚实锁 | pass | `feeds_evolution=false`；版本漂移 → `frozen=false` |
| Suite / Facade | pass | `run_evo_compute_g2_slice3_suite` / `run_evo_regression_gate` |

## 诚实锁

```text
g2_complete=false
certified=false
e2_claimed=false
feeds_evolution=false
production_sample=false
```

**未宣称**：生产回归集认证、G2/E2 完成、生产 L4。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_g2_slice3.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 回归 | `core/harness/evo_compute/regression.py` |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
