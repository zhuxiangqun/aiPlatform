# B1/B2 contract converge — standalone local

> Parent: [`B1_ROUTE_MATRIX.md`](../../../../docs/architecture/plans/B1_ROUTE_MATRIX.md) · [`EVAL_RUNTIME_CONTRACT.md`](../../../../docs/architecture/plans/EVAL_RUNTIME_CONTRACT.md)  
> Honesty: **standalone :8010** is the contract surface · Central **cohost D1** ≠ `temporary_proxy` · `process_split_authorized=false`

## What converged (local)

| Hook | Evidence |
|---|---|
| Unified error body (`code`/`runner_id`/`retryable`/`detail`) | `app/errors.py` + API 422/503 |
| sandbox / forbidden deny on enqueue | `execution_stubs` + tests |
| Worker dual-point reject forged jobs | `allowlist_guard.reject_forged_job` |
| temporary_proxy enabled markers = 0 in `app/` | `count_temporary_proxy_markers` |
| Upstream proxy is **store-only** | `eval_upstream` / `proxied_store_suffixes` |
| `/eval` UI copy for known codes | `evalExecutionErrors.ts` |
| wall-clock / cancel / cost → not `succeeded` | B2-L slices already shipped |

## Residual (not this gate)

| Item | Why |
|---|---|
| Central cohost still runs legacy in-process evals | Default D1 product path until staging authorize |
| Live microVM / S1 live attacks / B4-S | Host prerequisites |
| G2b accuracy | Separate unlock |

## Gate

```bash
bash packages/aiplat-evaluation/scripts/b12_contract_gate.sh
```
