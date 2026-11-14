---
doc_type: Reference
---

# Phase 0 失败处置表

> **计划**：[`docs/architecture/plans/eval-system-improvement-plan.md`](../../../../docs/architecture/plans/eval-system-improvement-plan.md) §4.1 / §5  
> **状态**：Phase 0 工程闸门绿 · Phase 1 已双人签字（首版 5/5 相对 SCOPE 可宣称）· **≠** 方案已定稿冻结 · **≠** 生产已独立  
> **开工日**：2026-11-14 · **更新**：2026-11-14（venv 3.11 基线 + CI 子集）

| 失败 ID | 症状/命令 | 类型 | 处置 | Owner | 退出条件 | 状态 |
|---|---|---|---|---|---|---|
| F-001 | `scorecard_v1_check` SHA mismatch SCORE_SCOPE | 断言过期 | editorial → manifest + `SHA_CHANGE_LOG` EV-2026-11-14-001 | 评测 owner | scorecard 绿 | **done** |
| F-002 | SHA mismatch G2B_PREP | 断言过期 | semantic index stub → 更新 SHA；不升 SCOPE | 评测 owner | 同上 | **done** |
| F-003 | SHA mismatch PREFERENCE_V0 | 断言过期 | editorial → 更新 SHA | 评测 owner | 同上 | **done** |
| F-004 | aggregate 产品级 `accuracy_claim=true` 字段冲突 | 实现 | 方案 A 拆字段 + closeout/g2b/UI/tests | 评测 owner | 产品级 false；scoped true | **done**（core 6 passed @ venv 3.11） |
| F-005 | calibration 指向已归档/gitignore human_pack | 数据 | preference→fixture；G2b→`g2b_tasks.v0`（可选 `AIPLAT_EVAL_G2B_FACILITATOR`） | 评测 owner | CI `test_calibration_human_pack` 绿 | **done**（2026-11-14 CI 复验：G2b 路径补齐） |
| F-006 | κ CLI n=100 vs 测试 30 → incomplete_pair | 数据 | `g2b_tasks.ci30.v0.json` | 评测 owner | κ 30 绿 | **done** |
| F-007 | core eval 基线（曾被系统 Py3.9 阻断） | 环境 | 使用仓库 `.venv`（3.11）重跑 | 评测 owner | core g2b 6 passed 有报告 | **done** |
| F-008 | package 全量曾缺 jwt / collect error | 环境 | `.venv` 全量：207 passed / 1 failed（F-009） | 评测 owner | 全量报告归档 | **done**（报告见 drills） |
| F-009 | arch gate 子进程硬编码 `python3`→系统 3.9 `kw_only` | 实现 | `PYTHON` 透传 + 测试注入 `sys.executable` | 评测 owner | arch 测绿；CI 子集绿 | **done** |
| F-010 | `g2b_n100_pack.sh` 死指已删目录 | 数据 | active n100 优先，archive fallback | 评测 owner | 脚本可解析先验 outputs | **done** |

## 0.0a / 0.5 证据

| 范围 | 结果 | 路径 |
|---|---|---|
| scorecard | PASS | — |
| core g2b（venv 3.11） | 6 passed | `drills/phase0-baseline-core-g2b-20261114T073858Z.txt` |
| package 全量（venv 3.11） | 207 passed → 修 F-009 后 arch 亦绿 | `drills/phase0-baseline-package-full-20261114T073900Z.txt` |
| CI 稳定子集门禁 | PASS（26 package + 6 core） | `scripts/phase0_ci_stable_subset.sh` · `PHASE0_CI_STABLE_SUBSET.md` |

## 汇总

```text
done：F-001…F-010
open：0（本轮处置表内）
CI 稳定子集：绿
仍禁止宣称：首版 5/5 已审计通过 / 方案已定稿 / 证据链「永久健康」
可写：执行基线已建立，Phase 0 进行中（稳定子集已钉死）
```

## 本轮追加（EV-2026-11-14-002）

| 项 | 状态 |
|---|---|
| `local_worksheets` → `_archive/...` | **done** |
| `accuracy_honesty_scan.py` 接入 CI 子集 | **done** |
| `.github/workflows/eval-phase0-stable.yml` | **done** |
| `package_release_check` 默认跑 Phase0 子集 | **done**（venv 已 PASS） |

## 进入 Phase 0.6 / Phase 1 前仍建议

```text
- 正式确认 R1–R9 设计勾选 + R10–R14 工件勾选（见计划 §15）
- 人工复核 SHA_CHANGE_LOG reviewer 栏
- 再宣称「可进入 Phase 1」须 scorecard + phase0_ci_stable_subset 持续绿
```
