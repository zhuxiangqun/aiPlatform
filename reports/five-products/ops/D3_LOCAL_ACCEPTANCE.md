# D3 Local Acceptance (all five)

- recorded_at: `20261101T015436Z`
- environment: `local`
- result: **PASS**
- production_signed: **false**
- authorize: **REFUSE paths covered per pack**

## Packs

| Capability | Script |
|------------|--------|
| aiplat | `packages/aiplat-central/scripts/d3_local_acceptance.sh` |
| fde | `packages/aiplat-fde/scripts/d3_local_acceptance.sh` |
| ontology | `packages/aiplat-ontology/scripts/d3_local_acceptance.sh` |
| evaluation | `packages/aiplat-evaluation/scripts/d3_local_acceptance.sh` |
| pi | `packages/aiplat-pi-runtime/scripts/d3_local_acceptance.sh` → `d3_local_closeout` |

## Commands

```bash
bash scripts/ops_d3_local_acceptance_all.sh
```

## Unfreeze

See [`ENGINEERING_UNFREEZE_D3_E2E.md`](./ENGINEERING_UNFREEZE_D3_E2E.md).
