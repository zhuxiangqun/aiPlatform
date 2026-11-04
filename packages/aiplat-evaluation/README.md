# aiplat-evaluation

Evaluation Service **D1 Thin (D1c/cohost)** · **D2 ops pack** · A3 Accepted（有条件）· **A1–A5 local standalone (closeout)**.

## Modes

| Mode | How | Notes |
|---|---|---|
| **cohost (default production)** | Central `GET /api/core/eval/healthz` | `deploy_unit=central` |
| **standalone (A1–A6 / B1–B3-L)** | `bash scripts/run_local.sh` → `:8010` | store OK; allowlist enqueue **202**; sandbox/forbidden **422**; **`process_split_authorized=false`**; `environment=local` |
| **B2-L worker** | `bash scripts/run_worker.sh` | poll `process_once` until idle/signal; same DB URL |
| **B3-L local_stub** | `AIPLAT_EVAL_SANDBOX_BACKEND=local_stub` | admits `http_probe` stub only; **no** network/container; see [`docs/a3/B3L_LOCAL.md`](./docs/a3/B3L_LOCAL.md) |
| **B3-L.3 docker cli** | `AIPLAT_EVAL_SANDBOX_BACKEND=docker` | admits `cli_probe` via allowlisted `docker run --network=none`; not microVM |
| **B3-L.2 dual-read** | `bash scripts/b3l_dual_read_drill.sh` | local fixture ETL + reconcile + pointer rollback; **not** production backfill |
| **Optional LLM** | `AIPLAT_EVAL_LLM=stub\|http` + BASE_URL | `prompt_eval` without Central; see [`docs/a3/LLM_LOCAL.md`](./docs/a3/LLM_LOCAL.md) |
| **LLM dynamic gate** | `bash scripts/b2l_llm_dynamic_gate.sh` | stub Worker e2e; optional live via `AIPLAT_EVAL_LLM_LIVE=1` |
| **Live LLM 10-task smoke** | `bash scripts/live_llm_smoke.sh` | stub baseline + optional live×3; see `docs/a3/LIVE_LLM_SMOKE.md` |
| **S1 security fixture** | `bash scripts/s1_local_gate.sh` | SECURITY_EVAL_V1 fixture ASR gate; **not** accuracy; see [`docs/a3/S1_LOCAL.md`](./docs/a3/S1_LOCAL.md) |
| **P1 scoring semantics** | `bash scripts/p1_local_gate.sh` | families + engineering composite (text/safety scored; asr report-only); `accuracy_claim=false`; see [`docs/a3/P1_LOCAL.md`](./docs/a3/P1_LOCAL.md) |
| **Local track closeout** | `bash scripts/local_track_closeout.sh` | P1+S1 gates + authorize locked; not B4/staging |
| **B4-S prep (blocked)** | [`docs/a3/B4S_PREP.md`](./docs/a3/B4S_PREP.md) | host prerequisites only; no authorize |
| **Scorecard evidence audit** | [`docs/a3/EVIDENCE_AUDIT_V1.md`](./docs/a3/EVIDENCE_AUDIT_V1.md) + `scripts/scorecard_v1_check.sh` | manifest SHA256 + dual-human attestation; refuse silent feature 5 |
| **microVM prep (blocked)** | [`docs/a3/MICROVM_PREP.md`](./docs/a3/MICROVM_PREP.md) + `scripts/microvm_local_prep_gate.sh` | probe + refuse live tools; no real isolation |
| **microVM Linux track** | [`docs/a3/MICROVM_LINUX_TRACK.md`](./docs/a3/MICROVM_LINUX_TRACK.md) + `scripts/microvm_linux_track_gate.sh` | KVM host admit + host allowlist CLI; Darwin ineligible |
| **microVM guest_boot authorize** | [`docs/a3/MICROVM_GUEST_BOOT.md`](./docs/a3/MICROVM_GUEST_BOOT.md) + `scripts/microvm_guest_boot_gate.sh` | GUEST_BOOT+KERNEL/ROOTFS+InstanceStart; ≠ process_split; Darwin ineligible |
| **microVM Linux track v1** | [`docs/a3/MICROVM_LINUX_TRACK.md`](./docs/a3/MICROVM_LINUX_TRACK.md) + `scripts/microvm_linux_track_gate.sh` | KVM host admit + host allowlist CLI; guest_boot deferred; Darwin ineligible |
| **G2b accuracy closeout** | [`docs/a3/G2B_ACCURACY_CLOSEOUT.md`](./docs/a3/G2B_ACCURACY_CLOSEOUT.md) + `scripts/g2b_accuracy_closeout_gate.sh` | adjudicated gold + pass-rate/CI; accuracy_claim=false until attestation |

| **B1/B2 contract converge** | `bash scripts/b12_contract_gate.sh` | error body + dual-point + temporary_proxy=0; see [`docs/a3/CONTRACT_LOCAL.md`](./docs/a3/CONTRACT_LOCAL.md) |
| **P1 canonical honesty** | `bash scripts/p1_canonical_gate.sh` | package scored vs Central legacy_7dim report-only; see [`docs/a3/P1_CANONICAL.md`](./docs/a3/P1_CANONICAL.md) |
| **Job wall-clock** | `AIPLAT_EVAL_JOB_TIMEOUT_SEC` (default 300) | exceed → `timed_out` (never succeeded) |
| **Job cancel** | `POST /api/platform/apps/eval/jobs/{id}/cancel` | queued\|running → `cancelled` |
| **Job cost cap** | `AIPLAT_EVAL_JOB_COST_CAP` / payload `cost_cap` | exceed → `timed_out` (`cost_cap_exceeded`) |
| **B1-L Compose + PG store** | `compose/docker-compose.b1l.yml` + `AIPLAT_EVAL_DB_URL=postgresql://…` | PG16 + MinIO; EvalStore via asyncpg; SQLite still default if unset |
| **Central proxy (optional)** | `AIPLAT_EVAL_SERVICE_URL=http://127.0.0.1:8010` | Central authenticates then forwards store subset |

## A5 closeout

```bash
bash packages/aiplat-evaluation/scripts/a5_local_closeout.sh
# backup / rollback / contracts / A4–A5 tests → docs/a3/drills/local-eval-a3-a5-closeout-*.json
```

See [`docs/a3/A_LOCAL_CLOSEOUT.md`](./docs/a3/A_LOCAL_CLOSEOUT.md).

## B2-L closeout

```bash
bash packages/aiplat-evaluation/scripts/b2l_local_closeout.sh
# allowlist + claim/execute + loop e2e → docs/a3/drills/local-eval-b2l-closeout-*.json
```

See [`docs/a3/B2L_LOCAL_CLOSEOUT.md`](./docs/a3/B2L_LOCAL_CLOSEOUT.md) · [`docs/a3/B2L_LOCAL.md`](./docs/a3/B2L_LOCAL.md).

## B3-L closeout

```bash
bash packages/aiplat-evaluation/scripts/b3l_local_closeout.sh
# stub/docker/dual-read + skill denied → docs/a3/drills/local-eval-b3l-closeout-*.json
```

See [`docs/a3/B3L_LOCAL_CLOSEOUT.md`](./docs/a3/B3L_LOCAL_CLOSEOUT.md).

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
- Unfreeze local: [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)
- B1-L runbook: [`docs/a3/B1L_LOCAL.md`](./docs/a3/B1L_LOCAL.md)
- Production plan: [`eval-production-independent-service.md`](../../docs/architecture/plans/eval-production-independent-service.md)

`process_split_authorized` stays **false** until B4-S/B6 (staging live + checklist). Local ≠ staging.
