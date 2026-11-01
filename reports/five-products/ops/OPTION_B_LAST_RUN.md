# Option B last full run

- recorded_at: `20261101T003405Z`
- command: `bash scripts/ops_option_b_all.sh` (+ Keycloak wait / OIDC re-sign)
- result: **PASS**
- pgha_mode: `docker` (PG :5433 + Keycloak :8081)
- environment: `local`
- staging_ready: **false**
- production_signed: **false**
- authorize: **not attempted**
- decision: [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md)
- tracks runlog: [`LOCAL_TRACKS_RUNLOG.md`](./LOCAL_TRACKS_RUNLOG.md)
- closeout: [`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md)

## Notes

- Prefer `pgha_mode=docker` (PG :5433 + Keycloak :8081).
- `pg_ha_local_staging.sh all` waits for Keycloak before OIDC.
- Hard gates remain false.
