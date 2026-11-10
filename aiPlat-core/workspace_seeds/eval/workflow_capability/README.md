# Workflow capability Case Pack (draft)

> Subject=`workflow` · `claim_eligible=false` · lexical fixture via `WorkflowSubjectAdapter`  
> Reuses engine `eval_sets/workflow/*` oracle patterns — **does not** fork Plan/EvalStore.

```bash
python3 -c "from core.api.core_facade import eval_validate_workflow_capability_bank, eval_run_workflow_capability_smoke; print(eval_validate_workflow_capability_bank()); print(eval_run_workflow_capability_smoke())"
```
