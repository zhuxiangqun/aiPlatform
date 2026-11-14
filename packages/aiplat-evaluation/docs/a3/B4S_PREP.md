---
doc_type: Reference
---

# B4-S prep — blocked until independent staging host

> Parent local unfreeze: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)  
> Staging unfreeze draft: [`ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING.md) (`draft_blocked`)  
> Scaffold page: [`B4S_STAGING_SCAFFOLD.md`](./B4S_STAGING_SCAFFOLD.md)  
> Honesty: **local track closed** · scaffold ≠ staging authorize · Chart still false

## Status

| Gate | State |
|---|---|
| Local B1–B3 / S1 / P1–P1.2 / dims / live_llm / session_v0+v1 / preference fixture | ✅ engineering complete on laptop（`local_track_closeout.sh` v2；G2b n=30 closeout 已完成、31–100 待双标） |
| Local B4-S rehearsal (Docker PG on :5434) | ✅ script PASS — [`B4S_LOCAL_REHEARSAL.md`](./B4S_LOCAL_REHEARSAL.md) · [`B4S_RUNBOOK.md`](./B4S_RUNBOOK.md) · evidence `local-eval-b4s-rehearsal-*.json` · **≠ staging evidence** |
| B4-S staging scaffold / unfreeze draft | ✅ opened · still `draft_blocked` |
| Independent staging host | ❌ **not confirmed** → B4-S **staging** blocked |
| PITR / backup live drill on staging | ❌ needs host |
| Production dual-read backfill | ❌ forbidden until B4 PITR |
| 政策 `process_split_authorized` | **true**（owner 覆盖；见 [`PHASE3_PROCESS_SPLIT_AUTHORIZE.md`](./PHASE3_PROCESS_SPLIT_AUTHORIZE.md)） |
| Chart `a3_process_split_authorized` | **false**（仍须 staging live 才翻） |

## Host prerequisites (D2)

1. Separate VM/cluster (not developer laptop) with durable disk.
2. PG with PITR / base backup + restore drill window.
3. JWKS IdP reachable from staging (Keycloak or enterprise).
4. Object store (MinIO/S3) for evidence blobs.
5. Network isolation from prod Central DB.

## Activation

Unfreeze draft already opened as **`draft_blocked`**:
[`ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING.md).  
Activate (`status=active`) **only** after host confirmed.  
Do **not** reuse the local-dev unfreeze to claim staging.

```bash
python3 packages/aiplat-evaluation/scripts/b4s_staging_scaffold_emit.py
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status
# ready_to_authorize must remain false without staging live evidence
```

## Out of scope here

- microVM / live skill tools — see [`MICROVM_PREP.md`](./MICROVM_PREP.md)
- G2b accuracy unlock
- Chart `a3_process_split_authorized=true`
