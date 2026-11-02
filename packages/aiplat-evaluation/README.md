# aiplat-evaluation

Evaluation Service **D1 Thin (D1c/cohost)** · **D2 ops pack** · A3 Accepted（有条件）· **A1/A2 local standalone**.

## Modes

| Mode | How | Notes |
|---|---|---|
| **cohost (default production)** | Central `GET /api/core/eval/healthz` | `deploy_unit=central` |
| **standalone (A1/A2 local)** | `bash scripts/run_local.sh` → `:8010` | independent SQLite; **`process_split_authorized=false`** |

## A2 local quickstart

```bash
bash packages/aiplat-evaluation/scripts/migrate_local.sh
bash packages/aiplat-evaluation/scripts/run_local.sh
# other terminal:
curl -fsS http://127.0.0.1:8010/healthz
curl -fsS http://127.0.0.1:8010/readyz
curl -fsS http://127.0.0.1:8010/api/platform/apps/eval/store/health
```

Tests (no server required):

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. python3 -m pytest tests/test_a1_standalone_healthz.py tests/test_a2_local_store.py -q
```

## Other

- Protocol: `eval.protocol.v0` · store schema: `eval.store.v0`
- Migrations: [`migrations/`](./migrations/)
- Install/upgrade/rollback/smoke: `scripts/d1_*.sh`
- D2 pack: [`docs/D2_COHOST.md`](./docs/D2_COHOST.md)
- A3 local plan: [`eval-a3-independent-service.md`](../../docs/architecture/plans/eval-a3-independent-service.md)
- Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md`](../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md)

`process_split_authorized` stays **false** until live checklist ✅ + staging (track B).
