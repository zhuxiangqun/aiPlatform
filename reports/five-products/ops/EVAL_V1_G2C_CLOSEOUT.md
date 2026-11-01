# EVAL_V1 G2c closeout — self-consistency（intra-rater）

- **closed_at**: `2026-11-02`
- **status**: **PASS**（工程校准；**非 accuracy**）
- **decision**: [`ENGINEERING_DECISION_EVAL_G2C_SELF_CONSISTENCY.md`](./ENGINEERING_DECISION_EVAL_G2C_SELF_CONSISTENCY.md)
- **unfreeze**: [`ENGINEERING_UNFREEZE_EVAL_G2C.md`](./ENGINEERING_UNFREEZE_EVAL_G2C.md)
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md)

## Delivered

| 项 | 证据 |
|---|---|
| `g2c.py` | Cohen κ + retest queue/record/report |
| API | `GET …/g2c-status` · `GET …/g2c-retest-queue` · `POST …/g2c-retest` · `POST …/g2c-report` |
| CoreFacade | `eval_g2c_status` / `eval_record_g2c_retest` / `eval_compute_g2c_report` |
| UI | `/eval?tab=settings` 标明 G2c ≠ accuracy ≠ G2b |
| tests | `core/tests/unit/test_eval_v1_g2c.py` |

## Honesty（强制）

| 字段 | 值 |
|---|---|
| `accuracy_claim` | **false**（永不 true） |
| `claim_kind` | `self_consistency` |
| `kappa_kind` | `intra_rater` |
| G2b | **仍 defer** |

禁止把 `intra_rater_kappa` 写成「第二标注者 κ」或 inter-annotator。

## Verify

```bash
pytest aiPlat-core/core/tests/unit/test_eval_v1_g2c.py -q
```
