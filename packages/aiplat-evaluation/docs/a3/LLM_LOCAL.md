# Eval Worker LLM (local optional)

> Contract: [`EVAL_MODEL_GATEWAY.md`](../../../../docs/architecture/plans/EVAL_MODEL_GATEWAY.md)  
> Honesty: `accuracy_claim=false` · no Central HTTP · no `core.harness` · not staging authorize

## Enable

| Env | Meaning |
|---|---|
| `AIPLAT_EVAL_LLM=0` | default — deterministic / require `payload.actual` |
| `AIPLAT_EVAL_LLM=stub` | offline stub (`AIPLAT_EVAL_LLM_STUB_OUTPUT`) |
| `AIPLAT_EVAL_LLM=1` + `AIPLAT_EVAL_LLM_BASE_URL` | OpenAI-compatible `POST …/chat/completions` |

Also: `AIPLAT_EVAL_LLM_API_KEY`, `AIPLAT_EVAL_LLM_MODEL`, `AIPLAT_EVAL_LLM_TIMEOUT`.

Provider must be **independent of Central process** (same physical host OK if separate lifecycle).

## Tests

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest tests/test_prompt_eval_llm.py -q
```
