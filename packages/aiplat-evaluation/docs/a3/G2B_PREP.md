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

### 0. 生成预填空表（推荐）

```bash
bash packages/aiplat-evaluation/scripts/human_worksheet_pack.sh
# → docs/a3/human_pack/<stamp>/ 含 g2b_facilitator + g2b_annotator_{a,b} + pref_*
```

1. 协调人**只编辑** `model_outputs.json`（扁平 `{ "g2b-01": "…" }`；可含换行/引号）。  
   **不要**往 `g2b_facilitator.json` 里手贴多行答案（易弄坏 JSON）。  
2. 同步到 facilitator + 两份标注表：

```bash
PYTHONPATH=packages/aiplat-evaluation python3 \
  packages/aiplat-evaluation/scripts/human_worksheet_pack.py \
  --from-outputs packages/aiplat-evaluation/docs/a3/human_pack/<stamp>
```

3. **只把** `g2b_annotator_a.json` / `g2b_annotator_b.json` 发给两名标注者（**不要**发 facilitator / `gold_pass_hint`）。  
4. 每人独立把 `pass: null` 改成 `true|false` + 可选 `notes`（盲标：不看对方、不看 gold）。  
5. 计算 κ：

```bash
PYTHONPATH=packages/aiplat-evaluation python3 \
  packages/aiplat-evaluation/scripts/g2b_kappa.py \
  --a path/to/annotator_a.json \
  --b path/to/annotator_b.json \
  --out packages/aiplat-evaluation/docs/a3/drills/local-eval-g2b-kappa-$(date -u +%Y%m%dT%H%M%SZ).json
```

6. 报告字段：`inter_annotator_kappa` · `accuracy_claim=false` · `not_accuracy_certification=true`。

## Exit

| Ready | Not ready |
|---|---|
| 两人各 ≥30 配对；κ 写出证据 JSON | 宣称 accuracy / 外部 gate / 同人填两份表 |

## Not claimed

≠ G2b closeout · ≠ staging · ≠ authorize · ≠ security cert
