# KB capability Case Pack (draft)

> Subject=`kb` · `claim_eligible=false` · retrieval fixture via `KbSubjectAdapter`  
> Oracle mirrors package `kb_rag` (hits / expected_ids) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ live RAG accuracy.

```bash
python3 -c "from core.api.core_facade import eval_validate_kb_capability_bank, eval_run_kb_capability_smoke; print(eval_validate_kb_capability_bank()); print(eval_run_kb_capability_smoke())"
```
