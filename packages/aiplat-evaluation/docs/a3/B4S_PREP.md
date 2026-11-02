# B4-S prep — blocked until independent staging host

> Parent unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Honesty: **local track closed** ≠ staging authorize · **does not** flip `process_split_authorized`

## Status

| Gate | State |
|---|---|
| Local B1–B3 / S1 / P1–P1.2 | ✅ engineering complete on laptop |
| Independent staging host | ❌ **not confirmed** → B4-S blocked |
| PITR / backup live drill | ❌ needs host |
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

- microVM / live skill tools (separate sandbox track)
- G2b accuracy unlock
- Chart `a3_process_split_authorized=true`
