---
doc_type: Reference
---

# Phase 3 · Tier A gold/gate 实跑账本

> 机器：[`evidence/meta_eval/phase3_tier_a_gold_gate_ledger.v0.json`](./evidence/meta_eval/phase3_tier_a_gold_gate_ledger.v0.json) · 2026-11-14T22:56:16+08:00
> n=**19** · evidence_ok=**19** · import_ok=**19** · claim_ready=**19**
> **诚实锁**：≠ security cert · Chart 仍 false · 禁止单一覆盖%

| 符号 | 家族 | evidence | import | claim_ready |
|---|---|:---:|:---:|:---:|
| `evaluate_judge_calibration_gate` | F1 | ✅ | ok | ✅ |
| `open_capability_judge_calibration` | F1 | ✅ | ok | ✅ |
| `judge_calibration_gate_for_ticket` | F1 | ✅ | ok | ✅ |
| `cohen_kappa_binary` | F1 | ✅ | ok | ✅ |
| `wilson_score_ci` | F1 | ✅ | ok | ✅ |
| `eval_judge_calibration_gate` | F1 | ✅ | ok | ✅ |
| `eval_open_capability_judge_calibration` | F1 | ✅ | ok | ✅ |
| `build_release_scorecard` | F4 | ✅ | ok | ✅ |
| `build_judge_calib_evidence_pack` | F4 | ✅ | ok | ✅ |
| `evaluate_security_judge_calibration` | F2 | ✅ | ok | ✅ |
| `load_judge_calib_defaults` | F2 | ✅ | ok | ✅ |
| `evaluate_security_family_gates` | F2 | ✅ | ok | ✅ |
| `eval_evaluate_security_judge_calibration` | F2 | ✅ | ok | ✅ |
| `eval_load_security_judge_calib_defaults` | F2 | ✅ | ok | ✅ |
| `eval_evaluate_security_family_gates` | F2 | ✅ | ok | ✅ |
| `eval_evaluate_security_severity_l5_gate` | F2 | ✅ | ok | ✅ |
| `assert_t13_process_split_boundary` | F3 | ✅ | ok | ✅ |
| `build_g2b_s_dual_review_workflow` | F3 | ✅ | ok | ✅ |
| `eval_assert_t13_process_split_boundary` | F3 | ✅ | ok | ✅ |

## 复跑

```bash
python3 packages/aiplat-evaluation/scripts/phase3_tier_a_gold_gate_ledger.py
```
