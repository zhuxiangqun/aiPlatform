---
doc_type: Reference
---

# Phase 0 CI 稳定子集（钉死清单）

> 来源：0.0a 基线（2026-11-14，`.venv` Python 3.11）  
> 规则：先全量基线，再从绿项中钉死 PR 门禁；全量失败进处置表，不得静默消失。  
> Gate：`scripts/phase0_ci_stable_subset.sh`

## PR 门禁（稳定子集）

```text
1) bash scripts/scorecard_v1_check.sh
2) package pytest（本清单）
3) core g2b unit（scheme A 诚实锁）
```

### Package tests

| 模块 | 理由 |
|---|---|
| `tests/test_scorecard_v1.py` | 记分卡诚实锁 |
| `tests/test_g2b_accuracy_closeout.py` | 方案 A 字段 + Wilson |
| `tests/test_g2b_kappa.py` | CI30 子集 κ |
| `tests/test_calibration_human_pack.py` | fixture 不依赖 archive |
| `tests/test_preference_v0.py` | preference 诚实锁 |
| `tests/test_arch_consolidation_v1.py` | 入口/架构 ratchet（须 `PYTHON=venv`） |
| `tests/test_p1_composite_semantics.py` | P1 计分 SSOT |

### Core tests

| 模块 | 理由 |
|---|---|
| `aiPlat-core/core/tests/unit/test_eval_g2b_pack_status.py` | 产品级 false / scoped true |
| `aiPlat-core/core/tests/unit/test_eval_g2b_l5_gap.py` | L5 gap / unlock 同方案 A |

## 全量 / nightly（不挡 PR）

```text
packages/aiplat-evaluation/tests/ 全量
platform eval E1（已含在 arch gate）
core eval 更广范围（另列；本机需 Py≥3.10 + deps）
```

## 基线证据

| 报告 | 结果 |
|---|---|
| `drills/phase0-baseline-core-g2b-20261114T073858Z.txt` | 6 passed |
| `drills/phase0-baseline-package-full-20261114T073900Z.txt` | 207 passed / 1 failed→F-009（arch 用系统 py3.9）→ 已修 PYTHON 透传 |
