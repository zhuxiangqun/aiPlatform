# Human preference / pairwise A/B v0

> Honesty: **`accuracy_claim=false`** · preference agreement ≠ accuracy certification

## What

| Item | Path |
|---|---|
| Pairs (32) | [`preference_pairs.v0.json`](./preference_pairs.v0.json) |
| Worksheet | [`preference_worksheet_template.json`](./preference_worksheet_template.json) |
| Score / κ | `scripts/preference_v0_report.py` |

## Procedure

1. Copy worksheet → `pref_a.json` / `pref_b.json`（可与 G2b 第二标注者并行）。
2. 每人选 `preferred: a|b|tie`。
3. 出报告：

```bash
PYTHONPATH=packages/aiplat-evaluation python3 \
  packages/aiplat-evaluation/scripts/preference_v0_report.py \
  --pairs packages/aiplat-evaluation/docs/a3/preference_pairs.v0.json \
  --a path/to/pref_a.json \
  --b path/to/pref_b.json \
  --out packages/aiplat-evaluation/docs/a3/drills/local-eval-preference-v0-$(date -u +%Y%m%dT%H%M%SZ).json
```

Solo（仅 A）也可用，只出 coverage，不报 inter-annotator κ。

## Not claimed

≠ G2b accuracy · ≠ RLHF production quality · ≠ authorize
