---
doc_type: Report
title: 生产加深 D1 — 活源适配器 + HUMAN_GATE 台账
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# 生产加深 D1

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md`；顺序：生产加深 → PSO。  
> 前置：G0–G3 Phase 切片已合入。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| 候选台账 | pass | `record_human_gate_decision` / `list_production_path_candidates` |
| 台账审计 | pass | `audit_human_gate_from_ledger`；`source=ledger` |
| 活评测/FDE 摘要 | pass | `summarize_live_*`；缺源 `unavailable` |
| Canary 探针 | pass | `probe_canary_rollout`；`cutover=false` |
| 基线→L4 levels | pass | `levels_from_baseline_loops`；缺测 `measured=false` |
| Facade 编排 | pass | `collect_evo_production_deepen_slice1` |
| deepen suite/gate | pass | complete/certified/e2 恒 false |

## 诚实锁

```text
g3_complete=false
g2_complete=false
certified=false
e2_claimed=false
production_write=false
canary cutover=false
```

**未宣称**：生产 holdout、真实切流 Canary、Gate G1–G3/E2 完成。

## 后续刀（登记，非本 PR）

1. **D2** — 试点真实 holdout 分区 → `compare_holdout`
2. **D3** — evo 候选 ↔ SkillRouter 灰度切流/回滚
3. **D4** — 活台账 HUMAN_GATE 100% + 已测 L4/缓释签批
4. **PSO** — 离线对照 DE/ES（加深完成后）

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_production_deepen_d1.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 台账 | `core/harness/evo_compute/candidate_ledger.py` |
| 活源 | `core/harness/evo_compute/live_sources.py` |
| 套件 | `core/harness/evo_compute/suite.py` |
| 门面 | `core/api/core_facade.py` |
