# B2-L — allowlist enqueue (local, not staging)

> Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Contract: [`EVAL_RUNTIME_CONTRACT.md`](../../../../docs/architecture/plans/EVAL_RUNTIME_CONTRACT.md)  
> Honesty: `environment=local` · `process_split_authorized=false`

## This slice

| Item | Status |
|---|---|
| Runner allowlist classify | ✅ `app/runner_allowlist.py` |
| API dual-point #1 (enqueue) | ✅ allowlist → **202** job; sandbox/forbidden → **422** |
| Jobs table `eval_jobs` | ✅ migration `0003_eval_jobs.sql` |
| Worker dual-point #2 | ✅ `reject_forged_job` → `dead_letter` |
| SKIP LOCKED claim / lease / heartbeat | ✅ `claim_next_job` / `heartbeat_job` / `process_once` |
| Allowlist runner execute | ✅ local deterministic (`replay_trace`/`prompt_eval`/…); LLM provider later |
| Worker poll loop | ✅ `run_worker_loop` + `scripts/run_worker.sh` / `python -m app.worker` |
| Local closeout | ✅ [`B2L_LOCAL_CLOSEOUT.md`](./B2L_LOCAL_CLOSEOUT.md) + `scripts/b2l_local_closeout.sh` |

## Allowed vs denied (B2)

- **Enqueue OK**: `replay_trace`, `prompt_eval`, `kb_rag`, `code_review_gold`, `arena`
- **422 sandbox_required**: `skill_suite`, `http_probe`, `cli_probe`, `security_redteam`
- **422 runner_forbidden**: any other `runner_id`

## Claim / lease / execute

```python
from app.worker import process_once
out = process_once(db_url, worker_id="w1")  # claim → allowlist → run → succeeded|failed
```

- Postgres: `FOR UPDATE SKIP LOCKED`
- SQLite: `BEGIN IMMEDIATE` + single-row claim
- Expired lease reclaimable; `attempts >= max_attempts` → `dead_letter`
- Wall-clock: `AIPLAT_EVAL_JOB_TIMEOUT_SEC` (default 300) → status `timed_out` (never `succeeded`)
- Cancel: `POST /api/platform/apps/eval/jobs/{id}/cancel` → `cancelled` (queued|running; cooperative vs Worker finalize)
- Cost hard-top: `AIPLAT_EVAL_JOB_COST_CAP` / payload `cost_cap` → `timed_out` + `cost_cap_exceeded` (never `succeeded`)
- Runners: local deterministic fixtures (`accuracy_claim=false`); `arena`+tools → `sandbox_required`
- Optional LLM: [`LLM_LOCAL.md`](./LLM_LOCAL.md) (`AIPLAT_EVAL_LLM=stub|http`) — accuracy_claim=false
- Dynamic LLM gate: `bash scripts/b2l_llm_dynamic_gate.sh`（stub e2e 必过；`AIPLAT_EVAL_LLM_LIVE=1` 可选真实独立 provider）

## Worker loop

```bash
# API (terminal A)
bash packages/aiplat-evaluation/scripts/run_local.sh

# Worker (terminal B) — drains allowlist jobs
AIPLAT_EVAL_WORKER_MAX_IDLE=5 bash packages/aiplat-evaluation/scripts/run_worker.sh
# or: cd packages/aiplat-evaluation && PYTHONPATH=. python3 -m app.worker
```

Env: `AIPLAT_EVAL_WORKER_ID`, `AIPLAT_EVAL_WORKER_IDLE_SLEEP`, `AIPLAT_EVAL_WORKER_MAX_JOBS`, `AIPLAT_EVAL_WORKER_MAX_IDLE`.

## Tests / closeout

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest \
  tests/test_b2l_allowlist_enqueue.py tests/test_b2l_claim_lease.py \
  tests/test_b2l_runner_execute.py tests/test_b2l_worker_loop.py \
  tests/test_b1l_execution_not_migrated.py -q

# Full B2-L local closeout (authorize stays false)
bash packages/aiplat-evaluation/scripts/b2l_local_closeout.sh
```
