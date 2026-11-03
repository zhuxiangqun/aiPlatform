# B4-S prep — blocked until independent staging host

> Parent unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Honesty: **local track closed** ≠ staging authorize · **does not** flip `process_split_authorized`

## Status

| Gate | State |
|---|---|
| Local B1–B3 / S1 / P1–P1.2 / dims / live_llm / session_v0+v1 / preference fixture | ✅ engineering complete on laptop（`local_track_closeout.sh` v2；human κ / G2b 仍 deferred） |
| Local B4-S rehearsal (Docker PG on :5434) | ✅ script PASS — [`B4S_LOCAL_REHEARSAL.md`](./B4S_LOCAL_REHEARSAL.md) · [`B4S_RUNBOOK.md`](./B4S_RUNBOOK.md) · evidence `local-eval-b4s-rehearsal-*.json` · **≠ staging evidence** |
| Independent staging host | ❌ **not confirmed** → B4-S **staging** blocked |
| PITR / backup live drill on staging | ❌ needs host |
| Production dual-read backfill | ❌ forbidden until B4 PITR |
| `process_split_authorized` | **false** (refuse until checklist + signed staging) |

## Host prerequisites (D2)

1. Separate VM/cluster (not developer laptop) with durable disk.
2. PG with PITR / base backup + restore drill window.
3. JWKS IdP reachable from staging (Keycloak or enterprise).
4. Object store (MinIO/S3) for evidence blobs.
5. Network isolation from prod Central DB.

## Activation

Only after host confirmed, open a **new** unfreeze:
`ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING` (name TBD).  
Do **not** reuse the local-dev unfreeze to claim staging.

```bash
# Still refuse on laptop:
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status
# ready_to_authorize must remain false without staging live evidence
```

## Out of scope here

- microVM / live skill tools — see [`MICROVM_PREP.md`](./MICROVM_PREP.md)
- G2b accuracy unlock
- Chart `a3_process_split_authorized=true`
