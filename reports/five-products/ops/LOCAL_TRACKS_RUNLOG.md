# Local tracks runlog (non-authorize)

- recorded_at: `20261101T003405Z`
- operator: `apple`
- environment: `local`
- option: **B (local VM/Docker)** — see [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md)
- production_signed: **false** (all tracks)
- authorize: **not attempted / not ready**

| Track | local_signed | latest |
|-------|:------------:|--------|
| pg_ha | true | `local-pgha-local-20261101T003405Z.json` |
| ontology_a3 | true | `local-ontology-a3-local-20261101T003320Z.json` |
| evaluation_a3 | true | `local-evaluation-a3-local-20261101T003320Z.json` |
| pi_d3 | true | `local-pi-d3-local-20261101T003320Z.json` |
| fde_field | true | `local-fde-field-local-20261101T003342Z.json` |

## Notes

- `local_signed` ≠ `production_signed`; checklist stays 🟨 for production.
- Re-run: `bash scripts/ops_option_b_all.sh`
