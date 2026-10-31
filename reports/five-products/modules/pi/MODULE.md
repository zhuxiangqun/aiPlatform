# MODULE.md — Pi Runtime

> Status: **D1 Thin + D2 admin** · D3 **Accepted（有条件）** · Owner: platform · Deploy unit: **Edge**

## Scope

- Load Artifact Bundle; local model execution; offline / POC runtime
- Healthz, install/upgrade/rollback (Gate3 Thin path)
- Optional enterprise reconnect (events / evidence out)

## Non-goals

- Multi-tenant enterprise governance
- Ontology authority or Evaluation engine
- Full five-process split beyond Gate3 Thin (ADR-09)

## Public API

- Bundle ingest (manifest + AGENT/SKILL)
- Local config + run control
- Evidence / event export schema

## Data owned

- Local runtime state, config, logs under `$AIPLAT_HOME` (device-local)
- Default: no upload of customer data

## Dependencies

- Shared kernel: Artifact Bundle contract, telemetry conventions
- **Forbidden**: FDE / Ontology / Evaluation / platform internal imports
- Center optional: identity client for reconnect only

## Deploy unit

- **Edge** — `packages/aiplat-pi-runtime`
- A3 already covered by Gate3 / ADR-08 Thin (no new A3 ADR required for Thin)

## SLO / disable behavior

- When disabled: host does not ship Pi package; other capabilities unaffected
- Offline-first: no center required for POC path

## CODEOWNERS

- `packages/aiplat-pi-runtime/ @platform`
- Chart / installer under same package

## D1 (Thin) — done

| Item | Path |
|------|------|
| Install | `packages/aiplat-pi-runtime/scripts/d1_install.sh` |
| Upgrade / rollback / backup | `d1_upgrade.sh` / `d1_rollback.sh` / `d1_backup.sh` |
| Smoke | `d1_smoke.sh` → `GET /healthz` |
| Docs | `packages/aiplat-pi-runtime/docs/INSTALL.md` |
| Contract | `packages/aiplat-pi-runtime/contracts/schemas/healthz.schema.json` |
| Rollback drill | `reports/five-products/GATE3_PI_THIN_ROLLBACK_DRILL.md` |

ADR-08 **not revised** — packaging only, no new update channel.

## D2 admin/security pack — done

| Item | Path |
|------|------|
| Baseline | `packages/aiplat-pi-runtime/security/baseline.yaml` |
| Check | `scripts/d2_admin_check.sh` |
| Docs | `docs/D2_ADMIN.md` |
| Chart | `chart/Chart.yaml` (`enterprise_default=0`) |

Default remains offline / `AIPLAT_ENTERPRISE=0`. Enterprise reconnect stays opt-in.

## D3 (Accepted 有条件 · 未授权生产宣称)

| Item | Path |
|------|------|
| ADR | `reports/five-products/ADR-PI-D3.md` |
| Checklist / prep | `docs/d3/D3_CHECKLIST.md` · `scripts/d3_prep_check.sh` |
| Local rehearsal | `d3_local_rehearsal` + `d3_soc_local_rehearsal`（#3–#6→🟨） |
| Live evidence | `docs/d3/LIVE_DRILL_EVIDENCE.md` · `d3_record_live_drill.sh` |
| Authorize | `scripts/d3_authorize.sh`（未全 ✅ → REFUSE） |

`d3_production_authorized: false` until checklist all ✅.

## Next

- **生产** SOC / bundle / N-1 live → checklist ✅ → `d3_authorize`
- Listed in Central D2 compat matrix
