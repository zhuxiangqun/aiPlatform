# Upgrade / rollback (stub)

## Upgrade

1. Backup DB + object store pointers.
2. Apply migrations (Alembic / product migrator).
3. Roll pods / process; check `/readyz`.
4. Smoke: contract sample + one product e2e.

## Rollback

1. Redeploy previous image tag / binary.
2. Reverse migration only if documented reversible; else restore backup.
3. Record incident in product runlog.

## Pi pointer (As-Is)

Reuse Gate3 drill: `reports/five-products/GATE3_PI_THIN_ROLLBACK_DRILL.md` +
`packages/aiplat-pi-runtime` compose/scripts — do not invent a parallel path in P0.
