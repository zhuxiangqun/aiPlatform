# Workflow capability Case Pack (draft)

> Subject=`workflow` · `claim_eligible=false` · lexical fixture via `WorkflowSubjectAdapter`  
> Reuses engine `eval_sets/workflow/*` oracle patterns — **does not** fork Plan/EvalStore.

## Layout

| Path | Role |
|---|---|
| `pack.meta.json` | Pack header |
| `cases/*.json` | Curated capability cases |
| `profile.workflow.smoke.v1.json` | Smoke Suite Profile |
| `profile.workflow.regression.v1.json` | Regression Suite Profile (`WORKFLOW_V1_CAPS` ×5) |

```bash
python3 -c "from core.api.core_facade import eval_validate_workflow_capability_bank, eval_workflow_regression_status; print(eval_validate_workflow_capability_bank()); print(eval_workflow_regression_status()['quota_inventory_ok'])"
```
