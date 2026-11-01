# templates/module/ (V2.1)

Per-capability packaging skeleton for
[`five-capability-independent-engineering-plan.md`](../../docs/architecture/plans/five-capability-independent-engineering-plan.md).

**Copy → fill diffs.** Second/third module = copy this tree + edit `module.yaml` / `MODULE.md`.

Packaging surface (D1/D2): [`PACKAGING_BASE.md`](./PACKAGING_BASE.md) · gate `bash scripts/check_five_products_packaging_surface.sh`.

## Required files (V2 §5 + V2.1 packaging)

| File | Purpose |
|------|---------|
| `MODULE.md` | Charter: scope, non-goals, API, data, deps, SLO, owner |
| `module.yaml` | Version, build/test entry, contracts, migrations |
| `Dockerfile` / `chart/` | Image + Helm stub |
| `contracts/` | Schema + sample validator |
| `docs/` / `runbooks/` / `uat/` | Delivery docs |
| `scripts/sbom-sign.stub.sh` | SBOM/sign placeholders |
| `scripts/d1_lib.sh` | D1 Thin helpers stub |
| `scripts/d2_admin_check.sh` | D2 security pack → shared baseline checker |
| `security/baseline.yaml` | D2 file/snippet baseline stub |
| `docs/PERF_BASELINE.md` | D2 local wall-clock budgets（非生产 SLA） |

## Levels

- **A1–A3**: autonomy (code → build → deploy). A3 needs ADR.
- **D1–D3**: delivery (deploy → docs/security → UAT harness).
- Do **not** reuse E0–E5 (evidence grades in landing plan).

## Deploy units (default 3, not 5)

```
Central: aiPlat + Ontology + Evaluation
Field:   FDE
Edge:    Pi
```

## Smoke

```bash
python3 templates/module/contracts/validate_sample.py
# helm lint templates/module/chart   # if helm installed
```

`templates/product/` is **superseded** by this tree (kept only as legacy pointer).
