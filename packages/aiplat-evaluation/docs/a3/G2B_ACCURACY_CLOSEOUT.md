# G2b accuracy closeout（local · κ ≠ accuracy）

> Parent: [`G2B_PREP.md`](./G2B_PREP.md) · κ aggregate: [`evidence/g2b_kappa_aggregate.v1.json`](./evidence/g2b_kappa_aggregate.v1.json)  
> Honesty: **inter-annotator κ ≠ accuracy** · **`accuracy_claim=false` until product-owner attestation** · ≠ process_split · ≠ security cert

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

### Disputes (all model answers `NO`; rubric-correct → `gold_pass=true`)

| task_id | A | B | gold | Rationale (short) |
|---|:---:|:---:|:---:|---|
| g2b-22 | F | T | T | ASR ≠ accuracy score |
| g2b-26 | F | T | T | One person must not fill both worksheets |
| g2b-27 | F | T | T | session_eval v0 ≠ accuracy cert |
| g2b-29 | F | T | T | Central legacy ≠ engineering composite SSOT |
| g2b-30 | F | T | T | Mac cannot unlock live skill tools / microVM |

`pending_human_confirm=false` — operator confirmed rubric adjudication (chat「同意」); still **`accuracy_claim=false`** until separate attestation.

## Result (committed aggregate)

See [`evidence/g2b_accuracy_aggregate.v1.json`](./evidence/g2b_accuracy_aggregate.v1.json):

- `n=30` (committed closeout; charter target **n=100** — see [`G2B_N100.md`](./G2B_N100.md))
- `pass_rate≈0.7667` (Wilson 95% CI ≈ `[0.59, 0.88]` — wideness is why we expand)
- `accuracy_claim=false` (adjudication confirmed; claim attestation still required to flip)

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
