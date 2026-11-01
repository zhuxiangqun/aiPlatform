# EVAL_V1 E3 — Gold set source inventory

- recorded_at: `2026-11-01`
- charter: [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md) §9
- unfreeze: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md)
- store: `EvalStore` / `bootstrap_e3_gold`（tenant `eval-v1`）

## Gate (E3 start)

| Gate | Rule | Status |
|------|------|--------|
| Runnable | ≥15 tasks in EvalStore | via `bootstrap_e3_gold` ← workspace seeds |
| Source inventory | this file | **done** |
| v0 lock | 30 tasks + solo adjudication | **not yet**（不挡 E3 启动；挡 G2a） |
| κ / accuracy | second annotator | **N/A**（D5） |

## Sources (v0 seed plan)

| # | Slice | Path / origin | Target count | Role |
|---|-------|---------------|--------------|------|
| 1 | code-review-gold batch | `aiPlat-core/workspace_seeds/eval/code_review_gold/batch_20_reviewbench.yaml` | ~40 | primary runnable (match_only predicted) |
| 2 | code-review-gold singles | `jwt_expiry_skew.yaml`, `sql_injection_auth.yaml` | 2（与 batch 去重） | overlap / fixture check |
| 3 | Hand-written fail cases | *pending human* — 工具错 / 路由错 / SOP 漏 | 10–15 | fill to 30 for v0 lock |
| 4 | Slice E2E / Gate3 | *optional later* | — | diversity |
| 5 | Agent/Skill redacted traces | *optional later* | — | diversity |

**Bootstrap command / API**

```bash
# library
python3 -c "from core.apps.eval.service.gold_bootstrap import bootstrap_e3_gold; print(bootstrap_e3_gold())"

# HTTP (canonical)
POST /api/platform/apps/eval/store/bootstrap-e3
```

## Review protocol (D5)

- Annotator id: `solo_reviewer`
- AI = pre-label / organize only；ground truth = human
- Arbitration window: Wed 19:00–21:00
- Do **not** report κ；do **not** claim accuracy
- Label fields: `pass` / `notes` / `status=pending_review|accepted|rejected`

## Honesty

E3 完成 = ≥15 可跑 + 本清单 + 复核队列打开。  
满 30 + 单人 adjudicated → 才可锁 v0 / 谈 G2a（仍不宣称 accuracy）。
