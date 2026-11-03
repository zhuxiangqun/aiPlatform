# Human preference / pairwise A/B v0

> Honesty: **`accuracy_claim=false`** · preference agreement ≠ accuracy certification

## What

| Item | Path |
|---|---|
| Pairs (32) | [`preference_pairs.v0.json`](./preference_pairs.v0.json) |
| Worksheet | [`preference_worksheet_template.json`](./preference_worksheet_template.json) |
| Eng fixture (solo) | [`fixtures/preference_solo_fixture.json`](./fixtures/preference_solo_fixture.json) — always `a`；≠ human |
| Score / κ | `scripts/preference_v0_report.py` |
| Gate | `scripts/preference_v0_gate.sh`（默认 fixture solo） |

## Procedure

### Engineering gate（CI / closeout）

```bash
bash packages/aiplat-evaluation/scripts/preference_v0_gate.sh
# coverage only; accuracy_claim=false; fixture≠human κ
```

### Human κ（真实标注）

0. 与 G2b 同一包生成（推荐）：

```bash
bash packages/aiplat-evaluation/scripts/human_worksheet_pack.sh
# 使用 pack 内 pref_annotator_a.json / pref_annotator_b.json
```

1. 把 `pref_annotator_*.json` 发给两名标注者（可与 G2b 同一对人，仍须盲标）。  
2. 每人把 `preferred: null` 改成 `a` | `b` | `tie`。  
3. 出报告：

```bash
AIPLAT_EVAL_PREF_A=path/to/pref_annotator_a.json \
AIPLAT_EVAL_PREF_B=path/to/pref_annotator_b.json \
bash packages/aiplat-evaluation/scripts/preference_v0_gate.sh
```

Solo（仅 A）也可用，只出 coverage，不报 inter-annotator κ。

## Not claimed

≠ G2b accuracy · ≠ RLHF production quality · ≠ authorize · fixture solo ≠ human κ
