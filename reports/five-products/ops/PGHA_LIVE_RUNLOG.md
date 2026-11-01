# PG/HA Live Kickoff Runlog

- recorded_at: `2026-11-01T03:12:00Z`（续 defer 复验）
- reviewed_at: `2026-11-01T11:12+08:00`（[`STAGING_REVIEW_2026-11-15.md`](./STAGING_REVIEW_2026-11-15.md)）
- decision: **continue_defer**
- drill_id: `pgha-live-defer-20261101`
- environment: `local`（诚实；**不是** staging）
- operator: `apple`
- cutover_authorized: **false** (unchanged)
- staging_ready: **false**
- review_by: **2026-11-22**

## Latest kickoff

```json
{
  "kind": "pgha_live_kickoff",
  "can_record": false,
  "blockers": [
    "missing AIPLAT_OIDC_ISSUER (or OIDC_ISSUER) for tenant login / MFA path",
    "AIPLAT_LIVE_DRILL_ENV='local' is not a production-class environment"
  ],
  "notes": [
    "DSN present (value redacted)",
    "docker_available=False (local/docker ≠ live authorize evidence)"
  ],
  "does_not_authorize": true
}
```

## Prerequisites / blockers

- [ ] Independent staging Postgres DSN（非 `127.0.0.1:5433`）
- [ ] `AIPLAT_OIDC_ISSUER` for tenant login / MFA path
- [ ] `AIPLAT_LIVE_DRILL_ENV=staging`（或 `prod-canary`）且与真实预发一致
- [ ] Operator / 变更窗口 / 回滚书面

Set e.g. **only on real staging host**:

```bash
export AIPLAT_LIVE_DRILL_ENV=staging
export AIPLAT_LIVE_DRILL_OPERATOR=$USER
export AIPLAT_PG_DSN='postgresql://…@staging-host/aiplat'
export AIPLAT_OIDC_ISSUER='https://…/realms/…'
bash scripts/ops_pgha_live_kickoff.sh
```

## Explicitly not done

- no checklist 🟨→✅
- no production_signed=true
- no cutover authorize
- no server purchase / staging provision this cycle

See [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) · [`LOCAL_DEFER.md`](./LOCAL_DEFER.md) · [`STAGING_REVIEW_2026-11-15.md`](./STAGING_REVIEW_2026-11-15.md).
