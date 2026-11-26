---
doc_type: Report
title: PSO 离线基线对照
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# PSO 基线对照

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` §8；架构 §5（PSO 仅基线）。  
> 前置：生产加深 D1–D3 已合入；D4 并行合入中。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| PSO 算子 | pass | `pso_velocity_update` / `pso_step` |
| 离线循环 | pass | `run_pso_offline`；预算硬停；代理适应度 |
| 对照摘要 | pass | `compare_pso_vs_de_es`；`pso_claimed_superior=false` |
| suite/gate | pass | `baseline_only`；g1_complete/certified/e2 恒 false |
| CoreFacade | pass | `run_evo_pso_offline` / `compare_evo_pso_vs_de_es` |

## 诚实锁

```text
baseline_only=true
pso_claimed_superior=false
g1_complete=false
certified=false
e2_claimed=false
production_write=false
```

**未宣称**：PSO 优于 DE/ES、G1/E2 完成、生产写入。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_pso_baseline.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 算法 | `core/harness/evo_compute/pso.py` |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
