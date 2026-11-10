# Tool/MCP capability Case Pack (draft)

> Subject=`tool` · `claim_eligible=false` · mock tool_trace via `ToolSubjectAdapter`  
> Oracle reuses `mock_tools` harness + `tool_trace_judge` (A3/A4/A5) — **does not** fork Plan/EvalStore  
> **Not** first-class `OBJECT_TYPES`; ≠ live tools / real MCP.

Catalog: default `agent_capability/fixtures/mock_tools/catalog.sample.json` (echo / lookup_fact).

```bash
python3 -c "from core.api.core_facade import eval_validate_tool_capability_bank, eval_run_tool_capability_smoke; print(eval_validate_tool_capability_bank()); print(eval_run_tool_capability_smoke())"
```
