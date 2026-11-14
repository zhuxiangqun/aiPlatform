---
doc_type: Reference
---

# Phase 3 · A_candidate 清单（工程预备）

> 机器：[`evidence/meta_eval/phase3_a_candidate_inventory.v0.json`](./evidence/meta_eval/phase3_a_candidate_inventory.v0.json) · 时点 2026-11-14T20:35:28+08:00
> **诚实锁**：本表 ≠ Tier A 扩容授权 · `tier_a_expansion_authorized=false`

## 汇总

- n=**19** · by_family={'F3': 3, 'F4': 2, 'F1': 7, 'F2': 7}
- 全部 `meta_family_green=true`（见 [`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md)）
- 全局 `tier_a_expansion_authorized=false`；按符号 scoped 见 [`PHASE3_TIER_A_AUTHORIZED.md`](./PHASE3_TIER_A_AUTHORIZED.md)

## 明细

| 符号 | 家族 | kind | impl | Tier A authorize |
|---|---|---|---|---|
| `assert_t13_process_split_boundary` | F3 | impl | `aiPlat-core/core/apps/eval/service/security_t13_allowlist.py:261` | **false** |
| `build_g2b_s_dual_review_workflow` | F3 | impl | `aiPlat-core/core/apps/eval/service/security_cert_prep.py:197` | **false** |
| `build_judge_calib_evidence_pack` | F4 | impl | `aiPlat-core/core/apps/eval/service/security_cert_prep.py:140` | **scoped true** |
| `build_release_scorecard` | F4 | impl | `aiPlat-core/core/harness/evaluation/release_scorecard.py:42` | **scoped true** |
| `cohen_kappa_binary` | F1 | impl | `aiPlat-core/core/apps/eval/service/g2c.py:30` | **false** |
| `eval_assert_t13_process_split_boundary` | F3 | facade_wrapper | `aiPlat-core/core/api/core_facade.py:8349` | **false** |
| `eval_evaluate_security_family_gates` | F2 | facade_wrapper | `aiPlat-core/core/api/core_facade.py:8021` | **scoped true** |
| `eval_evaluate_security_judge_calibration` | F2 | facade_wrapper | `aiPlat-core/core/api/core_facade.py:8095` | **scoped true** |
| `eval_evaluate_security_severity_l5_gate` | F2 | facade_wrapper | `aiPlat-core/core/api/core_facade.py:8255` | **false** |
| `eval_judge_calibration_gate` | F1 | facade_wrapper | `aiPlat-core/core/api/core_facade.py:10670` | **false** |
| `eval_load_security_judge_calib_defaults` | F2 | facade_wrapper | `aiPlat-core/core/api/core_facade.py:8158` | **scoped true** |
| `eval_open_capability_judge_calibration` | F1 | facade_wrapper | `aiPlat-core/core/api/core_facade.py:10705` | **false** |
| `evaluate_judge_calibration_gate` | F1 | impl | `aiPlat-core/core/apps/eval/service/capability_p4_gate.py:33` | **false** |
| `evaluate_security_family_gates` | F2 | impl | `aiPlat-core/core/apps/eval/service/security_family_report.py:428` | **scoped true** |
| `evaluate_security_judge_calibration` | F2 | impl | `aiPlat-core/core/apps/eval/service/security_judge_calib.py:321` | **scoped true** |
| `judge_calibration_gate_for_ticket` | F1 | impl | `aiPlat-core/core/apps/eval/service/capability_p4_gate.py:161` | **false** |
| `load_judge_calib_defaults` | F2 | impl | `aiPlat-core/core/apps/eval/service/security_judge_calib.py:61` | **scoped true** |
| `open_capability_judge_calibration` | F1 | impl | `aiPlat-core/core/apps/eval/service/capability_p4_gate.py:96` | **false** |
| `wilson_score_ci` | F1 | impl | `aiPlat-core/core/apps/eval/service/mode_intersection_rank.py:46` | **false** |

## 复跑

```bash
python3 packages/aiplat-evaluation/scripts/phase3_a_candidate_inventory.py
```

## 关联

- [`PHASE3_PREP.md`](./PHASE3_PREP.md)
- [`TIER_MATRIX_V0.md`](./TIER_MATRIX_V0.md)

