# MODULE.md — aiPlat Platform

> Status: **A2-versioning + D1 Thin + D2 compat/security** · Owner: platform · Target: **A2 / D2** · Deploy unit: **Central** (host)  
> Version: **0.1.0** · SSOT [`VERSIONING.md`](../../VERSIONING.md)

## Scope

- Agent / Skill / Workflow factory; enterprise runtime (tenant, quota, audit, governance)
- Identity / tenant authority; hosts Central co-deploy of Ontology + Evaluation by default
- Control-plane packaging (install, config, ops runbooks)

See [`CONTROL_PLANE.md`](./CONTROL_PLANE.md).

## Non-goals

- Ontology authority (consume Ontology API)
- FDE project system of record (consume Evidence / sync contracts)
- Evaluation scoring engine (host or call Evaluation Service)
- PG/HA/multi-tenant process split without ADR

## Public API

- Bundle registry, Identity, Tenant, Policy
- CoreFacade as sole platform→core entry
- Platform apps registry (`registry/apps.yaml`)
- Control plane v0 + `/api/core/healthz` (A1 host probe)

## Data owned

- Tenant / user / policy / Artifact / Run
- Runtime `$AIPLAT_HOME` layout (skills, agents, hooks, …) via `get_aiplat_home()` only

## Dependencies

- Shared kernel: contracts, identity, telemetry, config, test harness
- May **host** Ontology / Evaluation processes; must not import their internals
- **Forbidden**: business role / stage / artifact-key hardcodes in harness

## Deploy unit

- **Central** host — `aiPlat-platform` + `aiPlat-core` engine
- Package: `packages/aiplat-central`
- PG/HA → `pg_ha_adr_required: true`

## Contracts (A1)

| Schema | Path |
|--------|------|
| healthz | `contracts/schemas/healthz.schema.json` |
| Control plane v0 | `contracts/schemas/control_plane.schema.json` |
| validate | `python3 contracts/validate_sample.py` |

## Wiring (A1)

| Path | Behavior |
|------|----------|
| `GET /api/core/healthz` | A1 shape: `product_id=aiplat`, `hosted`, `control_plane` |
| `GET /api/core/health` | legacy dashboard (`status: healthy\|degraded`) — unchanged |
| Adapter | `core.harness.meta.control_plane` via `CoreFacade.aiplat_healthz_payload` |

## D1 (Thin) — done

| Item | Path |
|------|------|
| Install | `packages/aiplat-central/scripts/d1_install.sh` |
| Upgrade / rollback / backup | `d1_upgrade.sh` / `d1_rollback.sh` / `d1_backup.sh` |
| Smoke | `d1_smoke.sh` → `GET /api/core/healthz` |
| Docs | `packages/aiplat-central/docs/INSTALL.md` |
| Contract | `packages/aiplat-central/contracts/schemas/healthz.schema.json` |

PG/HA **not** in Thin — packaging + probe only.

## D2 (compat Thin) — done

| Item | Path |
|------|------|
| Matrix | `packages/aiplat-central/compat/matrix.yaml` |
| Check | `packages/aiplat-central/scripts/d2_compat_check.sh` |
| Docs | `packages/aiplat-central/docs/COMPAT.md` |

Covers Central + Pi + co-hosted Ontology/Eval + FDE PREP paths / versions / healthz `product_id`.

## D2+ (security baseline) — done

| Item | Path |
|------|------|
| Baseline | `packages/aiplat-central/security/baseline.yaml` |
| Check | `packages/aiplat-central/scripts/d2_security_check.sh` |
| Docs | `packages/aiplat-central/docs/SECURITY.md` |

Thin admin/security checklist (token middleware, admin MFA gate, Pi enterprise-off, FDE draft gate).

## SLO / disable behavior

- Individual hosted modules (FDE/Eval/Ontology) can be disabled; host stays up
- Identity/policy unavailable → fail closed on mutating APIs

## CODEOWNERS

- `aiPlat-platform/ @platform`
- `aiPlat-core/core/api/core_facade.py @platform`
- `packages/aiplat-central/ @platform`

## A2 versioning — done

| Item | Path |
|------|------|
| SSOT | `reports/five-products/versions.yaml` |
| Policy | `reports/five-products/VERSIONING.md` |
| Gate | `packages/aiplat-central/scripts/a2_version_check.sh` |

Package / module / SSOT locked at **0.1.0**. PG/HA still Draft ADR.

## PG/HA ADR — Accepted（有条件）

| Item | Path |
|------|------|
| ADR | `reports/five-products/ADR-CONTROL-PLANE-PG-HA.md` |
| Runbooks | `packages/aiplat-central/docs/pg_ha/` |
| Cutover | `CUTOVER_CHECKLIST.md` → `cutover_authorized=false` until green |

## D2 Thin local closeout — done (engineering)

| Item | Path |
|------|------|
| Scope | `packages/aiplat-central/docs/D2_THIN.md` |
| Closeout | `packages/aiplat-central/scripts/d2_local_closeout.sh` |
| Evidence | `reports/five-products/ops/AIPLAT_D2_THIN_LOCAL_CLOSEOUT.md` |

Aggregates A2 + compat + security + sibling D2 packs + install/N-1 + PG/HA local rehearsal; **cutover stays false**.

## Next

- **PG/HA 切流**勾齐 checklist + production_signed live 后再 authorize（预发复审 2026-11-08）
- Field compose 长驻另批
- D2++ deeper SOC/admin（可选；本地 perf baseline 已齐）
