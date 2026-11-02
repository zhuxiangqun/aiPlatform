# aiplat-evaluation

Evaluation Service **D1 Thin (D1c/cohost)** · **D2 ops pack** · A3 Accepted（有条件）· **A1–A5 local standalone (closeout)**.

## Modes

| Mode | How | Notes |
|---|---|---|
| **cohost (default production)** | Central `GET /api/core/eval/healthz` | `deploy_unit=central` |
| **standalone (A1–A5 local)** | `bash scripts/run_local.sh` → `:8010` | SQLite + canonical `/store/*`; **`process_split_authorized=false`** |
| **Central proxy (optional)** | `AIPLAT_EVAL_SERVICE_URL=http://127.0.0.1:8010` | Central authenticates then forwards store subset |

## A5 closeout

```bash
bash packages/aiplat-evaluation/scripts/a5_local_closeout.sh
# backup / rollback / contracts / A4–A5 tests → docs/a3/drills/local-eval-a3-a5-closeout-*.json
```

See [`docs/a3/A_LOCAL_CLOSEOUT.md`](./docs/a3/A_LOCAL_CLOSEOUT.md).

## A4 independence

```bash
bash packages/aiplat-evaluation/scripts/independence_check.sh
```

## A3 local quickstart

```bash
bash packages/aiplat-evaluation/scripts/migrate_local.sh
bash packages/aiplat-evaluation/scripts/run_local.sh
curl -fsS http://127.0.0.1:8010/healthz
```

Tests (no server required):

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. python3 -m pytest \
  tests/test_a1_standalone_healthz.py tests/test_a2_local_store.py \
  tests/test_a3_canonical_store_api.py tests/test_a4_independence.py \
  tests/test_a5_backup_rollback.py -q
```

## Other

- Protocol: `eval.protocol.v0` · store schema: `eval.store.v0`
- Migrations: [`migrations/`](./migrations/)
- D2 pack: [`docs/D2_COHOST.md`](./docs/D2_COHOST.md)
- A3 local plan: [`eval-a3-independent-service.md`](../../docs/architecture/plans/eval-a3-independent-service.md)
- Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md`](../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md)

`process_split_authorized` stays **false** until live checklist ✅ + staging (track B).
