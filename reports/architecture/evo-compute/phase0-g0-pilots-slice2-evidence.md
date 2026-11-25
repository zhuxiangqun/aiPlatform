---
doc_type: Report
title: Phase 0 / G0 — 三试点 + 预算/安全契约 + 夹具回放（slice-2）
status: active
authority: supporting
language: zh-CN
created: 2026-11-25
---
# Phase 0 / G0 pilots slice-2

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 0 / Gate G0 / §9–§11。  
> 底座：slice-1（Genome/Fitness/Sandbox/基线）已具备；本刀补试点选型与治理契约。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| 三试点 genome | pass | `routing.weights.v1` / `retrieval.params.v1` / `timeout.retry.v1` |
| 预算硬上限 | pass | `check_budget` 超限 `auto_stop`；默认 `approved=false` |
| 安全边界 | pass | 默认 `signed=false`；须人工 `sign_safety_boundary` |
| 夹具离线回放 | pass | 四分区夹具 → fitness → 沙箱；`production_sample=false` |
| G0 出口就绪 | pass | 缺预算/安全签字 → `phase0_complete=false` |
| CoreFacade | pass | `register_evo_pilot_genomes` / `replay_evo_candidate_offline` 等 |

## 诚实锁

```text
certified=false
e2_claimed=false
phase0_complete=false   # 直至人工批准预算 + 安全签字 + 试点/回放齐备
upgrade_claimed=false
```

**未宣称**：Phase 0 出口已过（须人工签字）、生产真实回放认证、DE/ES、Canary、E2、L4。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/ -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 试点 | `core/harness/evo_compute/pilots.py` |
| 预算 | `core/harness/evo_compute/budget.py` |
| 安全 | `core/harness/evo_compute/safety.py` |
| 回放 | `core/harness/evo_compute/replay.py` |
| 出口 | `core/harness/evo_compute/exit_readiness.py` |
| 门面 | `core/api/core_facade.py` |
