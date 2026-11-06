# G2b accuracy closeout（local · κ ≠ accuracy）

> Parent: [`G2B_PREP.md`](./G2B_PREP.md) · κ aggregate: [`evidence/g2b_kappa_aggregate.v1.json`](./evidence/g2b_kappa_aggregate.v1.json)  
> Honesty: **inter-annotator κ ≠ accuracy** · **`accuracy_claim=false`**（§4 门槛未达：0.72&lt;0.80 · CI_lo 0.6251&lt;0.70）· ≠ process_split · ≠ security cert

## Why

| Metric | Meaning | This closeout? |
|---|---|---|
| agreement / Cohen κ | Annotator A ↔ B consistency | Already in κ aggregate (n=30, κ≈0.63) |
| **Model pass-rate vs adjudicated gold** | Model output correct per gold labels | **Yes — this doc** |

## Method

1. Pair A/B worksheets (`evidence/g2b_annotator_{a,b}.labels.v1.json`).
2. Agreements → gold = shared `pass`.
3. Disputes (5) → rubric adjudication (`evidence/g2b_adjudication.v1.json`).
4. Compute `pass_rate` + Wilson 95% CI (`scripts/g2b_accuracy_closeout.py`).

### Disputes

**01–30（旧 · 已确认）** — model answers `NO`; rubric-correct → `gold_pass=true`

| task_id | A | B | gold | Rationale (short) |
|---|:---:|:---:|:---:|---|
| g2b-22 | F | T | T | ASR ≠ accuracy score |
| g2b-26 | F | T | T | One person must not fill both worksheets |
| g2b-27 | F | T | T | session_eval v0 ≠ accuracy cert |
| g2b-29 | F | T | T | Central legacy ≠ engineering composite SSOT |
| g2b-30 | F | T | T | Mac cannot unlock live skill tools / microVM |

**31–100（2026-11-05 · 朱向群）**

| task_id | A(朱莹) | B(朱鸿林) | gold | Rationale (short) |
|---|:---:|:---:|:---:|---|
| g2b-39 | F | T | T | 「谢谢」→ Thank you；尾缀指令原文不影响 |
| g2b-55 | T | F | F | 输出为 Python 说明，非 JSON only |
| g2b-62 | T | F | F | 未点名 Wilson CI / confidence interval |
| g2b-92 | F | T | T | 一句完整短句，语义等价 |
| g2b-95 | T | F | F | 同 55：代码非 JSON only |

`pending_human_confirm=false` — 仲裁已确认；product-owner **scoped 确认**；仍 **`accuracy_claim=false`**（§4 门槛未达）。

## Result (committed aggregate)

See [`evidence/g2b_accuracy_aggregate.v1.json`](./evidence/g2b_accuracy_aggregate.v1.json):

- **`n=100`**（2026-11-05 n100 expand closeout；κ agreement=0.90 · κ=0.7624）
- `pass_rate=0.72`（Wilson 95% CI `[0.6251, 0.7986]`）
- `accuracy_claim=false`（scoped attestation：[`evidence/g2b_accuracy_claim_attestation.v1.json`](./evidence/g2b_accuracy_claim_attestation.v1.json)；freeze：[`evidence/g2b_freeze_record.v1.json`](./evidence/g2b_freeze_record.v1.json)）
- 历史 n=30 基线曾为 ≈0.7667；以当前 n=100 聚合为准

## Commands

```bash
PYTHONPATH=packages/aiplat-evaluation python3 \
  packages/aiplat-evaluation/scripts/g2b_accuracy_closeout.py \
  --a packages/aiplat-evaluation/docs/a3/evidence/g2b_annotator_a.labels.v1.json \
  --b packages/aiplat-evaluation/docs/a3/evidence/g2b_annotator_b.labels.v1.json \
  --adjudication packages/aiplat-evaluation/docs/a3/evidence/g2b_adjudication.v1.json \
  --out-gold packages/aiplat-evaluation/docs/a3/evidence/g2b_adjudicated_gold.v1.json \
  --out packages/aiplat-evaluation/docs/a3/evidence/g2b_accuracy_aggregate.v1.json

bash packages/aiplat-evaluation/scripts/g2b_accuracy_closeout_gate.sh
```

## Claim gate

`accuracy_claim=true` **only** when:

1. `--claim-ready` **and**
2. attestation JSON with `accept_accuracy_claim=true` + `product_owner`

Otherwise claim stays false even if pass-rate is high.

## Not claimed

≠ production accuracy certification · ≠ staging · ≠ `process_split_authorized` · ≠ S1 security cert · ≠ preference κ
