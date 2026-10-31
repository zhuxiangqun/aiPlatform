# Local tracks runlog (non-authorize)

- recorded_at: `20261031T235857Z`
- operator: `apple`
- environment: `local`
- production_signed: **false** (all tracks)
- authorize: **not attempted / not ready**

| Track | local_signed | latest |
|-------|:------------:|--------|
| pg_ha | true | `local-pgha-local-20261031T235626Z.json` |
| ontology_a3 | true | `local-ontology-a3-local-20261031T235857Z.json` |
| evaluation_a3 | true | `local-evaluation-a3-local-20261031T235857Z.json` |

## Notes

- `local_signed` ≠ `production_signed`; checklist stays 🟨 for production.
- Re-run: `bash scripts/ops_local_rehearse_tracks.sh`
- PG/HA docker path: `AIPLAT_LOCAL_INCLUDE_PGHA=1 bash scripts/ops_local_rehearse_tracks.sh`
