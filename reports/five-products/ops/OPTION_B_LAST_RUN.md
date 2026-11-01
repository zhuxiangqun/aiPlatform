# Option B last full run

- recorded_at: `20261101T030630Z`
- command: `bash scripts/ops_option_b_all.sh`
- result: **PASS**
- pgha_mode: `docker`
- environment: `local`
- staging_ready: **false**
- production_signed: **false**
- authorize: **not attempted**
- decision: [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md)
- tracks runlog: [`LOCAL_TRACKS_RUNLOG.md`](./LOCAL_TRACKS_RUNLOG.md)
- closeout: [`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md)

## Notes

- Prefer `pgha_mode=docker` (PG :5433 + Keycloak :8081).
- If docker down: sqlite/file rehearsal still counts as Option B engineering; re-run after daemon up for full stack.
- Prior docker PASS sample: `evidence/local-pgha-local-20261031T235626Z.json`.
