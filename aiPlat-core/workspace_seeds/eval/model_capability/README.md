# Model capability Case Pack (draft)

> Subject=`model` · `claim_eligible=false` · lexical fixture via `ModelSubjectAdapter`  
> Reuses engine `eval_sets/model/*` oracle patterns — **does not** fork Plan/EvalStore.

```bash
python3 -c "from core.api.core_facade import eval_validate_model_capability_bank, eval_run_model_capability_smoke; print(eval_validate_model_capability_bank()); print(eval_run_model_capability_smoke())"
```
