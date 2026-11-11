# Multi-Agent capability Case Pack (draft)

> Subject=`multi_agent` · `claim_eligible=false` · fixture handoff via `MultiAgentSubjectAdapter`  
> Oracle: expected handoff path (+ optional final) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ live multi_agent runtime (M2 deferred).

| File | Role |
|------|------|
| `profile.multi_agent.smoke.v1.json` | Smoke Suite Profile (1× each MULTI_AGENT_V1_CAPS) |
| `profile.multi_agent.regression.v1.json` | Regression Suite Profile (`MULTI_AGENT_V1_CAPS` ×8) |

```bash
python3 -c "from core.api.core_facade import eval_validate_multi_agent_capability_bank, eval_multi_agent_regression_status; print(eval_validate_multi_agent_capability_bank()); print(eval_multi_agent_regression_status()['quota_inventory_ok'])"
```
