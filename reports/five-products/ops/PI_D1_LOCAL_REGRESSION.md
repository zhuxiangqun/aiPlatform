# Pi D1 Local Regression Runlog

- recorded_at: `20261101T003435Z`
- environment: `local` (not staging; **no** production_signed / authorize)
- demo_root: `/tmp/aiplat-pi-d1-20261101T003435Z`
- operator: `apple`
- result: **PASS**
- d3_production_authorized: **false** (unchanged)
- cutover_authorized: **false** (unchanged)

## Steps

| Step | Result |
|------|--------|
| d1_install --smoke | PASS |
| d1_smoke | PASS |
| d1_backup | PASS |
| d1_upgrade (distinct slot) | PASS (`versions/0.1.0+20261101T003436Z`) |
| d1_rollback --runtime | PASS (`versions/0.1.0`) |
| d1_rollback --bundle | PASS |
| Gate3 phase a/b/c | PASS |

## Notes

- Same package.json version re-upgrade uses `version+UTC` slot so runtime rollback flips.
- PG/HA / A3 / D3 live authorize remain deferred (`staging_ready=false`).

See [`LOCAL_DEFER.md`](./LOCAL_DEFER.md) · [`../GATE3_PI_THIN_ROLLBACK_DRILL.md`](../GATE3_PI_THIN_ROLLBACK_DRILL.md).
