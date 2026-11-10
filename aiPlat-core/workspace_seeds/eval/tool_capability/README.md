# Tool/MCP capability Case Pack (draft)

> Subject=`tool` · `claim_eligible=false` · mock tool_trace via `ToolSubjectAdapter`  
> Oracle reuses `mock_tools` harness + `tool_trace_judge` (A3/A4/A5) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ live tools / real MCP.

Catalog: default `agent_capability/fixtures/mock_tools/catalog.sample.json` (echo / lookup_fact).

| File | Role |
|------|------|
| `profile.tool.smoke.v1.json` | Smoke Suite Profile (1× each TOOL_V1_CAPS) |
| `profile.tool.regression.v1.json` | Regression Suite Profile (`TOOL_V1_CAPS` ×5) |

```bash
python3 -c "from core.api.core_facade import eval_validate_tool_capability_bank, eval_tool_regression_status; print(eval_validate_tool_capability_bank()); print(eval_tool_regression_status()['quota_inventory_ok'])"
```
