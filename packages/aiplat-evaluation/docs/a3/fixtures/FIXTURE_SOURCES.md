---
doc_type: Reference
---

# Eval fixtures — 来源 / 隐私 / 授权

> Phase 0 §4.6 · **禁止**把 `_archive/human_pack` 当作正式测试源回迁。

| Fixture | 来源 | 脱敏 | License | 用途 |
|---|---|---|---|---|
| `calibration/pref_annotator_a.v0.json` | `_archive/human_pack/20261103T130302Z/pref_annotator_a.json` | annotator_id 替换为 fixture；notes 清空；内容为合成问答 | internal-eval-use-only | `calibration_human_pack` preference 采样 |
| `../g2b_tasks.v0.json`（tracked 任务包） | 评测合成题面 | 无 PII | internal-eval-use-only | `calibration_human_pack` G2b 采样（**不用** gitignored `human_pack` facilitator） |
| `g2b_tasks.ci30.v0.json` | `g2b_tasks.v0.json` 前 30 题 | 无 PII（任务文本为评测合成） | internal-eval-use-only | `g2b_kappa` CI 子集 |
| `preference_solo_fixture.json` | 工程合成（非真人） | N/A（`not_human_annotation=true`） | internal-eval-use-only | preference gate 本地冒烟 |

本地若要在校准包里带上真实 `model_output`，设 `AIPLAT_EVAL_G2B_FACILITATOR=/path/to/g2b_facilitator.json`（仍不得把 raw human_pack 提交进仓）。

## 规则

```text
正式路径：docs/a3/fixtures/**
归档路径：docs/a3/_archive/**（只读历史）
新增 fixture PR：必须有 source/derived_from/license/desensitization（或显式 not_human）
```
