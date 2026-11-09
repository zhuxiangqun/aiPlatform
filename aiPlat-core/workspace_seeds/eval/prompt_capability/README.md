# Prompt capability Case Pack (draft)

> Subject=`prompt` · `claim_eligible=false` · lexical fixture via `PromptSubjectAdapter`  
> Reuses engine `eval_sets/prompt/*` oracle patterns — **does not** fork Plan/EvalStore.

## Layout

| Path | Role |
|---|---|
| `pack.meta.json` | Pack header |
| `cases/*.json` | Curated capability cases (`test_purpose` + `success_criteria`) |
| `profile.prompt.smoke.v1.json` | Smoke Suite Profile |

## Run

```bash
python3 -c "from core.api.core_facade import eval_list_prompt_capability_cases, eval_validate_prompt_capability_bank; print(eval_validate_prompt_capability_bank()); print(len(eval_list_prompt_capability_cases()))"
```

Live LLM path stays on `run_prompt_plan_exam(live=True)` — adapter execute is fixture-only.
