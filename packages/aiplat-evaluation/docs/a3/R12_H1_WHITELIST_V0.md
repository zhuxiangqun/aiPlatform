---
doc_type: Reference
---

# R12 · H1 白名单 v0（evaluation-system）

> 分诊：[`R12_TRIAGE_V0.md`](./R12_TRIAGE_V0.md)  
> Join 修复：CAPABILITIES = 反引号 ∪ 表格首列 → `in_both` 610→637  
> **本批**：27 个服务层精确符号补入 `AIPLAT_CAPABILITIES.md`（标记 `R12-H1`）  
> Honesty：`H1_candidate=0` ≠ 全平台覆盖完成；H5 仍有 open（多为域外 eval 样词）

---

## 结果（复跑后）

| 指标 | 值 |
|---|---:|
| registry 符号 | 638 |
| in_both | 637 |
| H1_candidate open | **0** |
| H2 exempt | 1 |
| H3 downgraded | 38 |
| H5 open | ~212（CAPABILITIES 中含 eval 样词但不在本域 provides） |

复跑：`python3 packages/aiplat-evaluation/scripts/r12_capability_reconciliation.py`

---

## 本批登记的 H1 符号（27）

`AgentSubjectAdapter` · `EvalSubjectAdapter` · `list_method_kinds` · `method_catalog` · `assert_subject_kinds_exclude_methods` · `run_*_capability_smoke`（13 个 Subject） · `annotate_family_asr_calibration` · `open_capability_judge_calibration` · `evaluate_t13_coverage` · `build_release_scorecard` · `held_model_for_task` · `summarize_library` · `summarize_online_samples` · `upsert_external_target` · `validate_mock_tool`

---

## 下一步

1. H5：收紧「eval 样词」匹配或按域过滤，避免把文档/ADR/面板算进对账分子  
2. 用 `in_both` 建 Tier A/B/C 矩阵（禁止从噪声 open 开干）  
3. 豁免到期 2027-02-14 复核 H2
