# Session capability Case Pack (draft)

> Subject=`session` · `claim_eligible=false` · multi-turn fixture via `SessionSubjectAdapter`  
> Oracle mirrors package `session_eval` (per-turn exact/non-empty + profile bounds) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ long-horizon Agent memory.

```bash
python3 -c "from core.api.core_facade import eval_validate_session_capability_bank, eval_run_session_capability_smoke; print(eval_validate_session_capability_bank()); print(eval_run_session_capability_smoke())"
```
