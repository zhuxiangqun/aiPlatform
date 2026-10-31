# aiplat-central chart (skeleton)

> ADR PG/HA **Accepted（有条件）**. `ha.enabled=false` / no DATABASE_URL until cutover checklist green.

```bash
# packaging only — do not helm upgrade production with ha.enabled=true yet
helm template aiplat-central packages/aiplat-central/chart
```

Release cadence: version = `packages/aiplat-central/package.json` (A2 SSOT 0.1.0).
