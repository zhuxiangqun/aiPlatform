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
- Runners: local deterministic fixtures (`accuracy_claim=false`); `arena`+tools → `sandbox_required`
- Live infra LLM (`AIPLAT_EVAL_LLM`) reserved — not required for this slice

## Tests

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest \
  tests/test_b2l_allowlist_enqueue.py tests/test_b2l_claim_lease.py \
  tests/test_b2l_runner_execute.py tests/test_b1l_execution_not_migrated.py -q
```
