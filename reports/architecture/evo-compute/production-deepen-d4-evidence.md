---
doc_type: Report
title: 生产加深 D4 — 活台账 HITL + 已测 L4/缓释签批
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# 生产加深 D4

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` 加深顺序 D4。  
> 前置：生产加深 D1–D3。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| D4 组装包 | pass | `collect_production_deepen_d4_pack`：ledger HITL + L4/缓释 |
| 诚实不可用 | pass | 缺 levels → `source=unavailable`；fixture HITL 不算 live 100% |
| Owner 签批 | pass | `sign_production_deepen_d4`；要求 `pack_ready`；落盘可选 |
| 就绪评估 | pass | `evaluate_production_deepen_d4_readiness`；`ready` 需 pack+signed |
| D4 suite/gate | pass | `g*_complete/certified/e2` 恒 false |
| CoreFacade | pass | 同名门面封装 |

## 诚实锁

```text
d4_signed=true 仅表示 deepen 包已 owner 签批
g3_complete=false
certified=false
e2_claimed=false
production_write=false
pack_ready≠gate claim
```

**未宣称**：G3/E2 完成、生产流量认证、配置写盘。

## 后续

PSO 离线对照 → ✅；工程轨收口 → ✅ D5（`production-deepen-d5-evidence.md`）。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_production_deepen_d4.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 签批 | `core/harness/evo_compute/deepen_signoff.py` |
| 台账 | `core/harness/evo_compute/candidate_ledger.py` |
| L4 | `core/harness/evo_compute/loops_l4.py` |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
