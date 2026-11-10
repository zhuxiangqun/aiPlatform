# Code Review capability Case Pack (draft)

> Subject=`code_review` · `claim_eligible=false` · gold set match via `CodeReviewSubjectAdapter`  
> Oracle mirrors package `code_review_gold` (findings vs gold exact set) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ live autoreview E2E.

```bash
python3 -c "from core.api.core_facade import eval_validate_code_review_capability_bank, eval_run_code_review_capability_smoke; print(eval_validate_code_review_capability_bank()); print(eval_run_code_review_capability_smoke())"
```
