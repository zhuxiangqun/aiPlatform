---
doc_type: Report
title: Phase 1 / G1 — DE/ES 离线 Orchestrator 最小切片
status: active
authority: supporting
language: zh-CN
created: 2026-11-25
---
# Phase 1 / G1 DE/ES slice-1

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 1 / Gate G1。  
> 前置：G0 底座 + 三试点 + 人工签批已合入。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| DE/ES 算子 | pass | `de_es.py`：init / DE / ES / 约束修复 / 代理适应度 |
| Evolution Orchestrator | pass | `run_de_es_offline`：种群循环 + 预算硬停 + 血缘 + ranked |
| Holdout 确认 | pass | `compare_holdout`（§10.2.1 最小；代理指标） |
| Human Gate / Canary / 回滚演练 | pass | 状态机演练；`production_write=false` |
| G1 suite / gate | pass | `run_evo_compute_g1_suite`；`g1_complete` 恒 false |
| CoreFacade | pass | `run_evo_de_es_offline` 等 |

## 诚实锁

```text
g1_complete=false   # 套件绿 ≠ Gate 宣称完成（出口就绪可另算）
certified=false
e2_claimed=false
production_write=false
production_sample=false
```

**未宣称**：生产流量 holdout 认证、真实 Canary 上线、E2、闭环已测 L4。  
适应度为**确定性代理**，非生产回放。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/ -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 算子 | `core/harness/evo_compute/de_es.py` |
| Orchestrator | `core/harness/evo_compute/orchestrator.py` |
| Holdout | `core/harness/evo_compute/holdout.py` |
| 演练 | `core/harness/evo_compute/drill.py` |
| 门面 | `core/api/core_facade.py` |
