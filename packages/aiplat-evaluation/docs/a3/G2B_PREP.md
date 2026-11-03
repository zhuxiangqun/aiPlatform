# G2b prep — second annotator pack（local）

> Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_G2B_PREP.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_G2B_PREP.md)  
> Honesty: **`accuracy_claim=false`** until a separate G2b closeout; κ alone ≠ accuracy certification

## What

| Item | Path |
|---|---|
| Task pack (30) | [`g2b_tasks.v0.json`](./g2b_tasks.v0.json) |
| Worksheet template | [`g2b_worksheet_template.json`](./g2b_worksheet_template.json) |
| κ script | `scripts/g2b_kappa.py` |

## Human procedure

1. Copy worksheet twice → `annotator_a.json` / `annotator_b.json`（互不共享）。
2. 每人独立对 30 条打 `pass: true|false` + 可选 `notes`（盲标：不看对方、不看 gold）。
3. 计算 κ：

```bash
PYTHONPATH=packages/aiplat-evaluation python3 \
  packages/aiplat-evaluation/scripts/g2b_kappa.py \
  --a path/to/annotator_a.json \
  --b path/to/annotator_b.json \
  --out packages/aiplat-evaluation/docs/a3/drills/local-eval-g2b-kappa-$(date -u +%Y%m%dT%H%M%SZ).json
```

4. 报告字段：`inter_annotator_kappa` · `accuracy_claim=false` · `not_accuracy_certification=true`。

## Exit

| Ready | Not ready |
|---|---|
| 两人各 ≥30 配对；κ 写出证据 JSON | 宣称 accuracy / 外部 gate / 同人填两份表 |

## Not claimed

≠ G2b closeout · ≠ staging · ≠ authorize · ≠ security cert
