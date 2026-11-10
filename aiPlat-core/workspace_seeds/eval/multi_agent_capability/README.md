# Multi-Agent capability Case Pack (draft)

> Subject=`multi_agent` · `claim_eligible=false` · fixture handoff path via `MultiAgentSubjectAdapter`  
> Oracle: `expected_handoff_path` exact edge sequence + optional `expected_final` — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; live multi_agent runtime remains **M2 deferred**.

```bash
python3 -c "from core.api.core_facade import eval_validate_multi_agent_capability_bank, eval_run_multi_agent_capability_smoke; print(eval_validate_multi_agent_capability_bank()); print(eval_run_multi_agent_capability_smoke())"
```
