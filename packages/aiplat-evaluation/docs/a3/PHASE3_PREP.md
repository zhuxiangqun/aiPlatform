---
doc_type: Reference
---

# Phase 3 预备（平台覆盖 · 未授权扩容）

> 计划 §8 · Tier 矩阵：[`TIER_MATRIX_V0.md`](./TIER_MATRIX_V0.md) · META：[`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md)  
> **诚实锁**：本页只做工程预备；**禁止**宣称「Tier A 已扩容 / 全平台已覆盖」  
> `tier_a_expansion_authorized=false` · `accuracy_claim=false` · `process_split_authorized=false`

---

## 前置（已满足 ≠ 授权）

| 条件 | 当前 |
|---|---|
| R12 tranche-1 H5 open=0 | ✅ |
| Tier 矩阵 v0（A_candidate 清单） | ✅ |
| META_EVAL F1–F4 `family_green` | ✅（[`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md)） |
| owner 授权扩 Tier A gate | **false**（未开） |

---

## A_candidate → META_EVAL 家族映射（首波预备）

| 家族 | 代表符号（摘录） | META | 扩容状态 |
|---|---|---|---|
| F1 Judge | `evaluate_judge_calibration_gate` · `open_capability_judge_calibration` · `cohen_kappa_binary` · `wilson_score_ci` | 绿 | **blocked**（待 authorize） |
| F2 Security | `evaluate_security_family_gates` · `evaluate_security_judge_calibration` · `evaluate_security_severity_l5_gate` | 绿 | **blocked**（≠ L5 declare） |
| F3 Boundary | `assert_t13_process_split_boundary` · `build_g2b_s_dual_review_workflow` | 绿 | **blocked**（≠ process_split） |
| F4 Scorecard | `build_release_scorecard` · `build_judge_calib_evidence_pack` | 绿 | **blocked** |

完整 19 个符号工程清单见 [`PHASE3_A_CANDIDATE_INVENTORY.md`](./PHASE3_A_CANDIDATE_INVENTORY.md) · [`evidence/meta_eval/phase3_a_candidate_inventory.v0.json`](./evidence/meta_eval/phase3_a_candidate_inventory.v0.json)。

---

## 本地可继续（不翻转 authorize）

1. ✅ 为每个 A_candidate 列：已有 gold / gate / 证据路径 / 缺口 → [`PHASE3_A_CANDIDATE_INVENTORY.md`](./PHASE3_A_CANDIDATE_INVENTORY.md)  
2. ✅ B 轨复核日历草稿 → [`PHASE3_B_REVIEW_CALENDAR.md`](./PHASE3_B_REVIEW_CALENDAR.md)  
3. ✅ 覆盖率报表骨架 A/B/C → [`PHASE3_COVERAGE_REPORT_SKELETON.md`](./PHASE3_COVERAGE_REPORT_SKELETON.md)  
4. ✅ 按符号扩容：A_candidate **19/19 scoped accepted**（[`PHASE3_TIER_A_AUTHORIZED.md`](./PHASE3_TIER_A_AUTHORIZED.md)）；**全局** `tier_a_expansion_authorized` 仍 **false**；`accuracy_claim` / `l5_declare` / `cert` / `process_split` 仍 false

## 禁止

| ❌ | ✅ |
|---|---|
| 一次全开 19 个 A_candidate | 单符号提案 + META 家族回链 |
| 把 `family_green` 写成 Tier A 已授权 | 保持 `tier_a_expansion_authorized=false` |
| 把 F2 绿写成 L5 / security cert | 安全认证另轨 |
| 把 F3 绿写成 process_split | 见 [`PHASE2_PREP.md`](./PHASE2_PREP.md) |

---

## Owner 授权前检查单（扩 1 个符号时）

- [ ] 符号在 `A_candidate`  
- [ ] 所属 META 家族仍绿  
- [ ] gold + gate 路径可复跑  
- [ ] 证据 `environment` 标签诚实  
- [ ] 变更写入 SHA / 修订记录  
- [ ] owner 明示 `tier_a_expansion_authorized` 仅对该符号

---

## 关联

- Phase 2（独立）：[`PHASE2_PREP.md`](./PHASE2_PREP.md)  
- Phase 3.5（尺子）：[`META_EVAL_V0.md`](./META_EVAL_V0.md)  
- 计划：`docs/architecture/plans/eval-system-improvement-plan.md` §8
