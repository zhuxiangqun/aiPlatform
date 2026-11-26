---
doc_type: Report
title: 生产加深 D3 — SkillRouter Canary 切流/回滚
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# 生产加深 D3

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` 加深顺序 D3。  
> 前置：生产加深 D1（只读探针）+ D2（holdout 分区）。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| Canary 桥 | pass | `request_evo_canary_cutover` / `observe_evo_canary` / `rollback_evo_canary` |
| 状态机对齐 | pass | `approved→canary` + `canary→rolled_back`；失败撤回注册 |
| 默认沙箱 | pass | 进程内 `SkillRouter()`；`use_global_router=True` 才全局并标 `production_write` |
| 循环 | pass | `run_evo_canary_cutover_rollback_cycle` |
| D3 suite/gate | pass | `g*_complete/certified/e2/production_write` 恒 false（默认） |
| CoreFacade | pass | 同名门面封装 |

## 诚实锁

```text
production_write=false（默认沙箱）
production_traffic=false
certified=false
e2_claimed=false
g1_complete=false
cutover=true 仅表示 Skill 灰度已注册（沙箱或显式全局）
```

**未宣称**：生产流量 Canary 上线、G1/E2 完成、配置文件写盘。

## 后续

D4 活 HITL/已测 L4 签批 → PSO 对照。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_production_deepen_d3.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 桥 | `core/harness/evo_compute/canary_bridge.py` |
| 路由 | `core/harness/deployment/canary.py`（SkillRouter） |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
