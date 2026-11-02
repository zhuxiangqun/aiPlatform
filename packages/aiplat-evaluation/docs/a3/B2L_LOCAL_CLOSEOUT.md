# EVAL A3 B2-L local closeout

> **status**: closeout evidence via `bash scripts/b2l_local_closeout.sh`  
> **Honesty**: `environment=local` · `process_split_authorized=false` · `staging_ready=false` · does **not** start B3 sandbox or B4-S staging  
> Contract: [`EVAL_RUNTIME_CONTRACT.md`](../../../../docs/architecture/plans/EVAL_RUNTIME_CONTRACT.md) §7  
> Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)

## Acceptance (B2-L / contract §7)

| # | Item | Result | Evidence |
|---|------|:------:|----------|
| 1 | enqueue rejects `skill_suite` / `http_probe` (unified body) | ✅ | closeout e2e + `test_b2l_allowlist_enqueue` |
| 2 | Worker dual-point rejects forged job (`dead_letter`) | ✅ | `test_worker_rejects_forged_skill_job` |
| 3 | `replay_trace` / `prompt_eval` / `kb_rag` / `code_review_gold` / `arena` local path | ✅ | deterministic runners; **live infra LLM deferred** (`accuracy_claim=false`) |
| 4 | lease expire reclaim / `max_attempts` → dead_letter | ✅ | `test_b2l_claim_lease` |
| 4b | wall-clock → `timed_out` (never succeeded) | ✅ | `test_b2l_job_wall_timeout` |
| 5 | import guard: no `core.harness` in `app/` | ✅ | closeout AST scan |
| 6 | Worker poll loop drains queue | ✅ | `run_worker_loop` e2e in closeout |
| 7 | `process_split_authorized` false | ✅ | healthz / authorize status / closeout JSON |

## Commands

```bash
bash packages/aiplat-evaluation/scripts/b2l_local_closeout.sh
# evidence → packages/aiplat-evaluation/docs/a3/drills/local-eval-b2l-closeout-*.json
```

## Exit

- B2-L **engineering proof complete** (enqueue → claim → execute → loop).
- **Not** B3 sandbox; **not** production split; **not** staging authorize.
- Next under same unfreeze: optional `AIPLAT_EVAL_LLM` for `prompt_eval`, then **B3-L** sandbox prototype.
