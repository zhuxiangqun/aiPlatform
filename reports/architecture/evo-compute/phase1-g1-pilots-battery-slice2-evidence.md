---
doc_type: Report
title: Phase 1 / G1 — 三试点 DE/ES 电池（slice-2）
status: active
authority: supporting
language: zh-CN
created: 2026-11-25
---
# Phase 1 / G1 pilots battery slice-2

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 1 / Gate G1 / §9。  
> 前置：G1 slice-1（单试点 Orchestrator）已合入。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| 三试点电池 | pass | `routing.weights.v1` / `retrieval.params.v1` / `timeout.retry.v1` 各跑 DE(+ES) |
| 可复现率汇总 | pass | `reproducible_rate`（门 ≥0.95） |
| 血缘 / 硬约束 | pass | `lineage_min≥1.0`；硬约束零回归 |
| Holdout≥1 | pass | 至少一个试点代理 holdout `significant` |
| Suite / Facade | pass | `run_evo_compute_g1_slice2_suite` / `run_evo_pilot_de_es_battery` |

## 诚实锁

```text
g1_complete=false
certified=false
e2_claimed=false
production_write=false
production_sample=false
```

**未宣称**：生产流量 holdout 认证、真实 Canary 上线、E2、闭环已测 L4。  
适应度仍为确定性代理。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_g1_slice2.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 电池 | `core/harness/evo_compute/battery.py` |
| 套件 | `core/harness/evo_compute/suite.py`（`run_evo_compute_g1_slice2_suite`） |
| 门面 | `core/api/core_facade.py` |
