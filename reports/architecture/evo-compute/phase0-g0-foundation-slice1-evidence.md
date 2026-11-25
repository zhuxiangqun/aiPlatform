---
doc_type: Evidence
title: Phase 0 / G0 — 受控演化底座最小切片（Genome + Fitness + Sandbox + 基线）
status: active
authority: evidence
language: zh-CN
created: 2026-11-25
---
# Phase 0 / G0 foundation slice-1

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 0 / Gate G0。  
> 状态机 SSOT：`docs/architecture/plans/aiplat-evolutionary-computation-architecture.md` §6。  
> 成熟度诚实锁：`docs/architecture/plans/aiplat-closed-loop-maturity.md` §3 / §7。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| Genome Registry | pass | `register_genome` / `get_genome` / `list_genomes` |
| Fitness Pareto→ranked | pass | `rank_candidates` + `scalar_v1` |
| Candidate 状态机 | pass | 含 `human_gate`；禁 `evaluated`；APPROVED≠SAFETY_PASSED |
| 离线沙箱 | pass | 预计算指标；`production_write=false` |
| 闭环 KPI 基线落盘 | pass | `measure_closed_loop_baseline`；缺测 `baseline_missing` |
| Suite / Gate | pass | `run_evo_compute_g0_suite` / `evaluate_evo_compute_g0_gate` |
| CoreFacade | pass | `register_evo_genome` 等 |

## 诚实锁

```text
certified=false
e2_claimed=false
phase0_complete=false
upgrade_claimed=false
```

**未宣称**：Phase 0 出口（G0 全过）、DE/ES 种群、Canary 生产、E2、闭环已测 L4。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_g0.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 包 | `aiPlat-core/core/harness/evo_compute/` |
| 门面 | `core/api/core_facade.py`（`register_evo_genome` / `run_evo_compute_g0_suite` 等） |
| 测试 | `core/tests/unit/test_harness/test_evo_compute/test_evo_compute_g0.py` |
