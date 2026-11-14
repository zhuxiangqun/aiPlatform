---
doc_type: Reference
---

# Phase 1 · 首版 5/5 可审计工作表

> **计划**：[`docs/architecture/plans/eval-system-improvement-plan.md`](../../../../docs/architecture/plans/eval-system-improvement-plan.md) §6  
> **范围**：相对 [`SCORE_SCOPE_V1.md`](./SCORE_SCOPE_V1.md) 的 in-scope 三轴  
> **诚实锁**：本表工程预检通过 **≠** 「首版 5/5 已审计通过」；须双人审计签字后才可写该宣称  
> **证据时点**：2026-11-14 · 分支 `eval/phase0-honesty-baseline` · Phase0 CI stable subset **PASS**（PR #737）

---

## 1. 工程预检（可复跑）

| # | 检查 | 命令 / 证据 | 结果 |
|---|---|---|---|
| P1-G1 | scorecard gate | `bash packages/aiplat-evaluation/scripts/scorecard_v1_check.sh` | **PASS** · feature/arch/local_no_microvm = 5.0 · `accuracy_claim=false` · dual_human=confirmed |
| P1-G2 | scheme A honesty | `python scripts/accuracy_honesty_scan.py`（包内） | **PASS** · product false / scoped true / not_cert true |
| P1-G3 | Phase0 CI 子集 | `bash scripts/phase0_ci_stable_subset.sh` + GH job | **PASS** 本地 26+6；PR #737 job green |
| P1-G4 | 处置表 open | [`PHASE0_FAILURE_DISPOSITION.md`](./PHASE0_FAILURE_DISPOSITION.md) F-001…F-010 | **open=0**（全部 done） |
| P1-G5 | manifest SHA 抽检 | 对 `evidence_manifest.v1.json` 含 `path+sha256` 条目复算 | **mismatch=0** · verified≈13 |
| P1-G6 | authorize 门禁 | `scorecard_v1.json` / manifest | `process_split_authorized=false` |
| P1-G7 | 禁宣扫描（产品文案） | Eval UI + a3 非 archive | 无「生产已独立」「准确率已认证」产品宣称 |

### 三轴（相对 SCORE_SCOPE_V1）

| 轴 | JSON 分 | 首版态度 | 预检 |
|---|---|---|---|
| feature_coverage | 5.0 | in-scope | 门禁绿 + dual_human confirmed + manifest |
| engineering_architecture | 5.0 | in-scope | 门禁绿 |
| local_independence_no_microvm | 5.0 | in-scope | 门禁绿；≠ authorize |
| local_independence_with_microvm | null | Darwin N/A | 不计首版 |
| production_independence | null / unscored | 不计首版 | gaps: staging / B4-S / B5 / B6 / SPLIT_CHECKLIST |

### 方案 A（准确率口径）

| 字段 | 期望 | 实测 |
|---|---|---|
| 产品级 `accuracy_claim` | false | false（scorecard / aggregate / honesty scan） |
| `scoped_accuracy_claim` | true（G2b n=100 + attestation） | true |
| `not_accuracy_certification` | true | true |
| `process_split_authorized` | false | false |

---

## 2. 审计人复核清单（人工）

审阅人须能独立完成：

1. 打开 `evidence/evidence_manifest.v1.json`，抽 ≥3 个 `sha256` 条目本地复算一致  
2. 核对 `dual_human_attestation.status=confirmed` 与 note 语义（κ ≠ accuracy）  
3. 核对 `g2b_accuracy_claim_attestation.v1.json` 为 **scoped** 接受，未提升产品级 claim  
4. 确认 UI/对外文档无「生产已独立 / 准确率已认证 / 首版 5/5 已审计通过」（在本签字完成前）  
5. 确认生产轴仍 unscored，缺口列表仍在

| 角色 | 姓名 | 日期 | 结论（pass / fail + 备注） |
|---|---|---|---|
| 审计人 A | ________________ | ________ | ________ |
| 审计人 B | ________________ | ________ | ________ |

**双人均 pass 后**才允许在计划 / SCORECARD 中写：「首版 5/5 已审计通过（相对 SCORE_SCOPE_V1；产品 accuracy_claim=false；≠ authorize）」。

---

## 3. 当前可写 / 不可写

```text
可写：
  可进入 Phase 1
  Phase 1 工程预检通过（工作表 §1）
  执行基线已建立；Phase0 CI 稳定子集绿

不可写（至 §2 双人签字前）：
  首版 5/5 已审计通过
  方案已定稿 / 已冻结
  生产已独立 / 准确率已认证
  process_split_authorized=true
```
