# B3-L — sandbox local_stub (local, not staging)

> Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Contract: [`EVAL_RUNTIME_CONTRACT.md`](../../../../docs/architecture/plans/EVAL_RUNTIME_CONTRACT.md)  
> Honesty: `environment=local` · `process_split_authorized=false` · **`sandbox_real_isolation=false`**

## This slice

| Item | Status |
|---|---|
| Sandbox policy `off` / `local_stub` | ✅ `app/sandbox/policy.py` |
| Admit `http_probe` under local_stub | ✅ enqueue 202 + Worker execute |
| In-process stub (no network I/O) | ✅ `runners/http_probe.py` |
| Deny `skill_suite` / `cli_probe` / redteam | ✅ still `sandbox_required` |
| Real container / microVM | ❌ deferred |
| Data dual-read migration drill | ❌ deferred (B3-L.2) |

## Enable

```bash
export AIPLAT_EVAL_SANDBOX_BACKEND=local_stub
bash packages/aiplat-evaluation/scripts/run_local.sh
# Worker:
AIPLAT_EVAL_SANDBOX_BACKEND=local_stub bash packages/aiplat-evaluation/scripts/run_worker.sh
```

Default backend is `off` (B2 behavior unchanged).

## Tests

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest tests/test_b3l_sandbox_local_stub.py -q
```
