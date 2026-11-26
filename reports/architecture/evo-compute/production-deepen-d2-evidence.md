---
doc_type: Report
title: 生产加深 D2 — 版本化 Holdout 分区
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# 生产加深 D2

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` §10.2.1 / 加深顺序 D2。  
> 前置：生产加深 D1。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| Holdout 种子/落盘 | pass | `default_pilot_holdout_seed` / `load_holdout_partition` / `install_pilot_holdout_seeds` |
| 分区打分 | pass | `score_genes_on_holdout_batches`（确定性；非生产流量） |
| compare_holdout | pass | 优先 dataset；可标 `surrogate` / `unavailable` |
| D2 suite/gate | pass | `production_traffic/certified/e2` 恒 false |
| CoreFacade | pass | `load_evo_holdout_partition` / `install_evo_pilot_holdout_seeds` |

## 诚实锁

```text
production_traffic=false
certified=false
e2_claimed=false
g1_complete=false（套件锁定）
source=dataset_seed|dataset_disk|surrogate|unavailable
```

**未宣称**：生产流量 holdout 确认、G1/E2 完成。

## 后续

D3 Canary 切流/回滚 → D4 活 HITL/L4 → PSO。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_production_deepen_d2.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 数据集 | `core/harness/evo_compute/holdout_dataset.py` |
| 对比 | `core/harness/evo_compute/holdout.py` |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
