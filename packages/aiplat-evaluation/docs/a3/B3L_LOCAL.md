---
doc_type: Reference
---

# B3-L — sandbox local_stub + docker cli (local, not staging)

> Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Contract: [`EVAL_RUNTIME_CONTRACT.md`](../../../../docs/architecture/plans/EVAL_RUNTIME_CONTRACT.md)  
> Honesty: `environment=local` · `process_split_authorized=false` · **`sandbox_real_isolation=false`**

## This slice

| Item | Status |
|---|---|
| Sandbox policy `off` / `local_stub` / `docker` | ✅ `app/sandbox/policy.py` |
| Admit `http_probe` under local_stub | ✅ enqueue 202 + Worker execute |
| In-process stub (no network I/O) | ✅ `runners/http_probe.py` |
| Admit `cli_probe` under docker | ✅ B3-L.3 — allowlist argv + `docker run --network=none` |
| Admit `skill_suite` fixture-only | ✅ B3-L.4 — `mode=fixture` / cases; **tools still denied** |
| Deny live skill tools / redteam | ✅ still `sandbox_required` |
| microVM / live skill tools | ❌ deferred — prep only: [`MICROVM_PREP.md`](./MICROVM_PREP.md) |
| Data dual-read migration drill | ✅ B3-L.2 — `scripts/b3l_dual_read_drill.sh` |
| Local closeout | ✅ [`B3L_LOCAL_CLOSEOUT.md`](./B3L_LOCAL_CLOSEOUT.md) + `scripts/b3l_local_closeout.sh` |

## Enable

```bash
# stub http_probe only
export AIPLAT_EVAL_SANDBOX_BACKEND=local_stub

# docker cli_probe (+ http_probe stub)
export AIPLAT_EVAL_SANDBOX_BACKEND=docker
# optional: AIPLAT_EVAL_DOCKER_BIN / AIPLAT_EVAL_SANDBOX_IMAGE=alpine:3.20

bash packages/aiplat-evaluation/scripts/run_local.sh
AIPLAT_EVAL_SANDBOX_BACKEND=docker bash packages/aiplat-evaluation/scripts/run_worker.sh
```

Default backend is `off` (B2 behavior unchanged). Without a docker binary, `cli_probe` stays denied even if backend=`docker`.

## Dual-read (B3-L.2)

```bash
bash packages/aiplat-evaluation/scripts/b3l_dual_read_drill.sh
```

## Tests / closeout

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest \
  tests/test_b3l_sandbox_local_stub.py \
  tests/test_b3l_sandbox_docker_cli.py \
  tests/test_b3l_dual_read.py -q

bash packages/aiplat-evaluation/scripts/b3l_local_closeout.sh
```
