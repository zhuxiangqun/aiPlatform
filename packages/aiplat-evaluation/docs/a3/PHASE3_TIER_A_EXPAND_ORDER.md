---
doc_type: Reference
---

# Phase 3 · Tier A 单符号扩序（建议）

> 机器：[`evidence/meta_eval/phase3_tier_a_expand_order.v0.json`](./evidence/meta_eval/phase3_tier_a_expand_order.v0.json)  
> **诚实锁**：本序 ≠ 已授权；每次只开 1 个；全局 `tier_a_expansion_authorized` 默认仍 false（按符号记账）

## 原则

1. **先尺子后门禁**：F1 judge → F4 scorecard → F2 security → F3 boundary  
2. **先 impl 后 facade**：`evaluate_*` / `build_*` 先于 `eval_*` 包装  
3. **一次一个**：上一个 owner 签字后，才开下一个提案  
4. **F2/F3 绿 ≠ L5 / process_split**：扩序里单独标注禁区

## 顺序

| # | 符号 | 家族 | 状态 |
|---:|---|---|---|
| 1 | `evaluate_judge_calibration_gate` | F1 | **accepted** → [`PHASE3_TIER_A_AUTHORIZED.md`](./PHASE3_TIER_A_AUTHORIZED.md) |
| 2 | `open_capability_judge_calibration` | F1 | **accepted** |
| 3 | `judge_calibration_gate_for_ticket` | F1 | **accepted** |
| 4 | `cohen_kappa_binary` | F1 | **accepted** |
| 5 | `wilson_score_ci` | F1 | **accepted** |
| 6 | `eval_judge_calibration_gate` | F1 | **accepted**（facade） |
| 7 | `eval_open_capability_judge_calibration` | F1 | **accepted**（facade） |
| 8 | `build_release_scorecard` | F4 | **accepted** |
| 9 | `build_judge_calib_evidence_pack` | F4 | **accepted** |
| 10 | `evaluate_security_judge_calibration` | F2 | **accepted**（≠ L5） |
| 11 | `load_judge_calib_defaults` | F2 | **accepted** |
| 12 | `evaluate_security_family_gates` | F2 | **accepted**（≠ cert） |
| 13 | `eval_evaluate_security_judge_calibration` | F2 | **accepted**（facade） |
| 14 | `eval_load_security_judge_calib_defaults` | F2 | **accepted**（facade） |
| 15 | `eval_evaluate_security_family_gates` | F2 | **accepted**（facade） |
| 16 | `eval_evaluate_security_severity_l5_gate` | F2 | **accepted**（facade；`l5_declare` false） |
| 17 | `assert_t13_process_split_boundary` | F3 | **accepted**（`process_split` false） |
| 18 | `build_g2b_s_dual_review_workflow` | F3 | **accepted** |
| 19 | `eval_assert_t13_process_split_boundary` | F3 | **提案中**（facade · 末）→ [`PHASE3_TIER_A_PROPOSAL_eval_assert_t13_process_split_boundary.md`](./PHASE3_TIER_A_PROPOSAL_eval_assert_t13_process_split_boundary.md) |

## 关联

- 清单：[`PHASE3_A_CANDIDATE_INVENTORY.md`](./PHASE3_A_CANDIDATE_INVENTORY.md)  
- 预备：[`PHASE3_PREP.md`](./PHASE3_PREP.md)
