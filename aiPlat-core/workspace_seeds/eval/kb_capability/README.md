# KB capability Case Pack (draft)

> Subject=`kb` · `claim_eligible=false` · retrieval fixture via `KbSubjectAdapter`  
> Oracle mirrors package `kb_rag` (hits / expected_ids) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ live RAG accuracy.

| File | Role |
|------|------|
| `profile.kb.smoke.v1.json` | Smoke Suite Profile (1× each KB_V1_CAPS) |
| `profile.kb.regression.v1.json` | Regression Suite Profile (`KB_V1_CAPS` ×5) |

```bash
python3 -c "from core.api.core_facade import eval_validate_kb_capability_bank, eval_kb_regression_status; print(eval_validate_kb_capability_bank()); print(eval_kb_regression_status()['quota_inventory_ok'])"
```
