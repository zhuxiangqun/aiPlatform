# Session capability Case Pack (draft)

> Subject=`session` · `claim_eligible=false` · multi-turn fixture via `SessionSubjectAdapter`  
> Oracle mirrors package `session_eval` (per-turn exact/non-empty + profile bounds) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ long-horizon Agent memory.

| File | Role |
|------|------|
| `profile.session.smoke.v1.json` | Smoke Suite Profile (1× each SESSION_V1_CAPS) |
| `profile.session.regression.v1.json` | Regression Suite Profile (`SESSION_V1_CAPS` ×5) |

```bash
python3 -c "from core.api.core_facade import eval_validate_session_capability_bank, eval_session_regression_status; print(eval_validate_session_capability_bank()); print(eval_session_regression_status()['quota_inventory_ok'])"
```
