---
doc_type: Reference
---

# Phase 0 · §15 勾选建议稿（供产品/评测 owner 确认）

> **计划**：[`docs/architecture/plans/eval-system-improvement-plan.md`](../../../../docs/architecture/plans/eval-system-improvement-plan.md) §15  
> **性质**：执行方建议，**不是**自动定稿；owner 签字后才算正式勾选  
> **证据时点**：2026-11-14 · `.venv` Python 3.11  
> **门禁实测**：`scorecard_v1_check` PASS · `accuracy_honesty_scan` PASS · `phase0_ci_stable_subset` PASS · `package_release_check` PASS

---

## 如何用这份建议

```text
1. 审阅人逐行看「建议」列
2. 同意则把计划 §15.2 / 本表「完成勾选」改为 ☑，并签 reviewer
3. 不同意则批注；禁止无签字批量改 ☑
4. R1–R9 与 R10–R14 语义不同（设计 vs 条件+工件）——勿混
```

---

## R1–R9（设计审核）

| # | 项 | 建议 | 完成勾选 | 证据 / 说明 |
|---|---|---|---|---|
| R1 | 阶段顺序 | **建议 ☑ 正式通过** | ☐ 待 owner | 计划结构未改；0→1→2→3/3.5→4 |
| R2 | 方案 A 拆字段 | **建议 ☑ 正式通过** | ☐ 待 owner | 设计正确；**落地已完成**（见下「落地」） |
| R3 | SHA 变更控制 | **建议 ☑ 正式通过** | ☐ 待 owner | `SHA_CHANGE_LOG.md` EV-001/002 |
| R4 | 失败处置表 | **建议 ☑ 正式通过** | ☐ 待 owner | `PHASE0_FAILURE_DISPOSITION.md` F-001…F-010 done |
| R5 | Tier 分层 | **建议 ☑ 正式通过** | ☐ 待 owner | 计划 §4.5；实施在 Phase 3 |
| R6 | 元评测必须 | **建议 ☑ 正式通过** | ☐ 待 owner | 计划 §4.4 阈值已写；实施在 Phase 3.5 |
| R7 | Phase 0.6 禁宣称 | **建议 ☑ 正式通过** | ☐ 待 owner | 文首诚实锁仍有效 |
| R8 | 生产独立门禁 | **建议 ☑ 正式通过** | ☐ 待 owner | `process_split_authorized=false` 未动 |
| R9 | §16 第一步 | **建议 ☑ 正式通过** | ☐ 待 owner | 已按 §16 执行完毕 |

**R2 落地核对（≠ 仅设计）**

| 消费方 | 状态 |
|---|---|
| `g2b_accuracy_aggregate.v1.json` | `accuracy_claim=false` · `scoped_accuracy_claim=true` · `not_accuracy_certification=true` · refuse 非空 |
| `scorecard_v1.json` | `accuracy_claim=false` |
| `evidence_manifest.v1.json` | `accuracy_claim=false` · method 注明 scheme A |
| attestation | scoped accept 保留 |
| tests（package + core g2b） | 断言产品级 false / scoped true |
| `g2b.py` / CoreFacade 路径 | 同方案 A |
| EvalG2bPanel + glossary | 展示 scoped 字段 |
| `accuracy_honesty_scan.py` | gate ok |

---

## R10–R14（条件 + 工件）

| # | 项 | 建议 | 完成勾选 | 工件路径 |
|---|---|---|---|---|
| R10 | 0.0a 全量基线先于 CI 子集 | **建议 ☑ 完成**（工件齐） | ☐ 待 owner | `drills/phase0-baseline-package-full-*.txt` · `phase0-baseline-core-g2b-*.txt` · `PHASE0_CI_STABLE_SUBSET.md` |
| R11 | 元评测初始阈值 + owner | **仅条件接受；暂不勾完成** | ☐ | 阈值在计划 §4.4；**缺 owner 签字页**（建议下表） |
| R12 | 能力对账 | **仅条件接受；暂不勾完成** | ☐ | 规则在计划 §4.5；**尚无差异清单/数量/处理结果**（Phase 3 起步） |
| R13 | 证据版本与回滚 | **建议 ☑ 完成**（Phase 0 证据链） | ☐ 待 owner | `evidence_version` / `change_id` / `SHA_CHANGE_LOG` rollback 字段 |
| R14 | fixture 隐私/来源 | **建议 ☑ 完成** | ☐ 待 owner | `fixtures/FIXTURE_SOURCES.md` · `fixtures/calibration/` · `g2b_tasks.ci30.v0.json` |

### R11 owner 签字栏（填后可勾完成）

| 字段 | 值 |
|---|---|
| 阈值版本 | 计划 §4.4 初值（agreement≥0.80 / κ≥0.60 / ECE≤0.10 / gold 抽样错误率≤5%） |
| Owner | ________________ |
| 签字日 | ________________ |
| 备注 | 可调阈值须走 SHA/semantic 变更控制 |

---

## 门禁快照（建议勾选时附上）

```text
PYTHON=.venv/bin/python bash packages/aiplat-evaluation/scripts/phase0_ci_stable_subset.sh
→ PASS（scorecard + honesty scan + 26 package + 6 core）

PYTHON=.venv/bin/python bash packages/aiplat-evaluation/scripts/package_release_check.sh
→ PASS version=0.1.0 authorize=false
```

---

## 汇总建议（给 owner 的一句话）

```text
R1–R9：建议全部正式 ☑（设计确认）
R10 / R13 / R14：建议 ☑（工件已齐）
R11：待你签阈值 owner 栏后再 ☑
R12：留到 Phase 3 对账结果产出后再 ☑

在 R1–R9 + R10/R13/R14 正式勾选、且门禁持续绿之前：
  可写：执行基线已建立，Phase 0 进行中（稳定子集已钉死）
  不可写：方案已定稿 / 首版 5/5 已审计通过
```

### Owner 确认区

| 角色 | 姓名 | 日期 | 确认范围 |
|---|---|---|---|
| 产品 owner | | | R1–R9 / R11 |
| 评测 owner | | | R3–R4 / R10 / R13–R14 |
| 备注 | | | |
