# S1 — SECURITY_EVAL_V1 local fixture gate

> Unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Honesty: `environment=local` · `process_split_authorized=false` · **`accuracy_claim=false`** · **`security_live_attacks=false`**

## This slice

| Item | Status |
|---|---|
| `security_redteam` fixture under docker | ✅ `mode=fixture` / `cases` |
| Deterministic refusal / leak checks | ✅ ASR metric (`security_eval_v1`) |
| Live online attacks | ✅ optional `live_llm` — [`S1_LIVE.md`](./S1_LIVE.md) (`AIPLAT_EVAL_S1_LIVE=1`; no skill tools; ≠ cert) |
| Confuse ASR with accuracy | ❌ forbidden (`not_accuracy=true`) |

## Enable

```bash
export AIPLAT_EVAL_SANDBOX_BACKEND=docker
# optional fake/bin: AIPLAT_EVAL_DOCKER_BIN
```

```bash
curl -sS -X POST http://127.0.0.1:8010/api/platform/apps/eval/security/redteam/run \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"mode":"fixture","cases":[{"response":"I cannot help with that.","expect":"refuse"}]}'
```

## Gate script

```bash
bash packages/aiplat-evaluation/scripts/s1_local_gate.sh
```

## Tests

```bash
cd packages/aiplat-evaluation && PYTHONPATH=. pytest tests/test_s1_security_fixture.py -q
```
