# B1-L — local standalone (not staging)

> Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Honesty: `environment=local` · `process_split_authorized=false` · not staging evidence

## What this slice delivers

| Item | Status |
|---|---|
| Store/read on `:8010` | ✅ (A2–A6) |
| Dynamic execute routes | ✅ **503** + unified `error` body |
| Compose PG16 + MinIO | ✅ infra up (`compose/docker-compose.b1l.yml`) |
| PG-backed EvalStore adapter | ⏳ next B1-L slice |
| Keycloak full realm | ⏳ optional; JWKS/HS256 already (A6/B0) |

## Run API (SQLite default)

```bash
bash packages/aiplat-evaluation/scripts/run_local.sh
curl -fsS http://127.0.0.1:8010/healthz
# expect: environment=local, process_split_authorized=false, b1l_execution_stubs=true
```

## Dynamic execute → 503

```bash
TOKEN=$(python3 -c "from app.auth import mint_local_token; print(mint_local_token(tenant_id='t'))")
# from packages/aiplat-evaluation with PYTHONPATH=.
curl -sS -o /tmp/e.json -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{}' http://127.0.0.1:8010/api/platform/apps/eval/skill-evals/suites/s1/run
# 503 + {"error":{"code":"execution_not_migrated","runner_id":"skill_suite",...}}
```

## Compose sidecars

```bash
cd packages/aiplat-evaluation
docker compose -f compose/docker-compose.b1l.yml up -d postgres minio
# postgres: localhost:5433  user/pass/db=eval/eval_local/eval
# minio:    localhost:9000  console :9001
```

## Tests

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest tests/test_b1l_execution_not_migrated.py -q
```

## UI note

`/eval` should treat `error.code=execution_not_migrated` as “执行平面尚未迁移（B2）”; store/read remain usable.
