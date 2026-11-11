# Code Review capability Case Pack (draft)

> Subject=`code_review` · `claim_eligible=false` · gold set match via `CodeReviewSubjectAdapter`  
> Oracle mirrors package `code_review_gold` (findings vs gold exact set) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ live autoreview E2E.

| File | Role |
|------|------|
| `profile.code_review.smoke.v1.json` | Smoke Suite Profile (1× each CODE_REVIEW_V1_CAPS) |
| `profile.code_review.regression.v1.json` | Regression Suite Profile (`CODE_REVIEW_V1_CAPS` ×8) |

```bash
python3 -c "from core.api.core_facade import eval_validate_code_review_capability_bank, eval_code_review_regression_status; print(eval_validate_code_review_capability_bank()); print(eval_code_review_regression_status()['quota_inventory_ok'])"
```
