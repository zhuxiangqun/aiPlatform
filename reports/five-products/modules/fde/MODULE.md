# MODULE.md — FDE Workbench

> Status: **A1 + Field D1 Accepted + Field D2 ops pack** · Owner: platform · Target: **A2 / D2** · Deploy unit: **Field**  
> Version: **0.1.0** · ADR: [`ADR-FDE-FIELD-DEPLOY.md`](../../ADR-FDE-FIELD-DEPLOY.md)

## Scope

- Customer-site delivery: project / requirements / implementation / tasks / evidence / acceptance
- Local-first; Bundle import; evidence export; optional sync to center
- Field deployable unit (`packages/aiplat-fde`)

See [`FIELD_SCOPE.md`](./FIELD_SCOPE.md).

## Non-goals

- Own Runtime / Ontology / Evaluation engines
- Parallel signoff path
- Compose long-running (另批)
- PG/HA control-plane cutover（另见控制面 ADR）

## Public API

- Bundle import, Evidence export (`fde.evidence.v0`)
- Signoff **唯一**: `POST /api/platform/apps/fde/acceptance/signoff`
- Healthz: `GET /api/core/fde/healthz` (`production_field=true`)

## Field D1 — done

| Item | Path |
|------|------|
| Package | `packages/aiplat-fde` |
| Install / backup / rollback / smoke | `scripts/d1_*.sh` |
| N-1 | `docs/N1_COMPAT.md` |
| Data residency | `docs/DATA_RESIDENCY.md` |
| ADR | `ADR-FDE-FIELD-DEPLOY.md` **Accepted** |

## Field D2 ops pack — done (local)

| Item | Path |
|------|------|
| Scope | `packages/aiplat-fde/docs/D2_FIELD.md` |
| Upgrade / runtime rollback | `scripts/d1_upgrade.sh` · `d1_rollback.sh --runtime` |
| Security baseline | `security/baseline.yaml` · `scripts/d2_admin_check.sh` |
| Local closeout | `scripts/d2_local_closeout.sh` · [`ops/FDE_FIELD_D2_LOCAL_CLOSEOUT.md`](../../ops/FDE_FIELD_D2_LOCAL_CLOSEOUT.md) |

`capabilities.manifest` **current_delivery** 仍为 **D1**（D2 = Field ops pack，与 Pi D2 admin 同级叙事）。

## CODEOWNERS

- `aiPlat-platform/apps/fde/ @platform`
- `packages/aiplat-fde/ @platform`

## Next

- Optional independent process / compose（另 ADR）
- A2 deeper Field productization（非本 pack）
