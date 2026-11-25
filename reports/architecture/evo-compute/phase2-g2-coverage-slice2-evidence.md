---
doc_type: Report
title: Phase 2 / G2 — 评测/FDE 覆盖实测路径（slice-2）
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---
# Phase 2 / G2 coverage slice-2

> 实施权威：`docs/architecture/plans/aiplat-evolution-implementation-plan.md` Phase 2 / Gate G2。  
> 前置：G2 slice-1（离散 GA + 缺测诚实探针）已合入。

## 本刀交付

| 项 | 状态 | 说明 |
|---|---|---|
| 库存覆盖率 | pass | `coverage_ratio_from_inventory` / `measure_*_from_inventory` |
| 能力报告映射 | pass | `measure_eval_coverage_from_capability_report`（Harness 不直导 apps） |
| Facade 桥接 | pass | `collect_evo_eval_coverage_from_capability_report` → eval 分析 |
| G2 slice-2 suite | pass | 夹具达标可驱动 exit_readiness；套件 `g2_complete=false` |
| 缺测路径 | pass | 无库存时仍 `baseline_missing` |

## 诚实锁

```text
g2_complete=false   # 套件/门禁恒 false（夹具 ≠ 生产 L4 宣称）
certified=false
e2_claimed=false
fixture_thresholds ≠ production claim
```

**未宣称**：生产评测 L4 ≥90%、生产 FDE 证据 ≥95%、G2/E2 完成。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra \
  python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_evo_compute/test_evo_compute_g2_slice2.py -q
```

## 核心路径

| 层 | 路径 |
|---|---|
| 覆盖 | `core/harness/evo_compute/coverage.py` |
| 套件 | `core/harness/evo_compute/suite.py`（`run_evo_compute_g2_slice2_suite`） |
| 门面 | `core/api/core_facade.py` |
