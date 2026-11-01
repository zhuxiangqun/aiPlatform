# D2 local performance baseline

- recorded_at: `2026-11-01`
- result: **PASS**（contract budgets）
- production SLA: **no**

## Gate

```bash
bash scripts/check_five_products_perf_baseline.sh
# optional smokes:
AIPLAT_PERF_INCLUDE_SMOKE=1 bash scripts/check_five_products_perf_baseline.sh
```

## Docs

| Package | Doc |
|---------|-----|
| central | `packages/aiplat-central/docs/PERF_BASELINE.md` |
| pi | `packages/aiplat-pi-runtime/docs/PERF_BASELINE.md` |
| fde | `packages/aiplat-fde/docs/PERF_BASELINE.md` |
| ontology | `packages/aiplat-ontology/docs/PERF_BASELINE.md` |
| evaluation | `packages/aiplat-evaluation/docs/PERF_BASELINE.md` |

## Non-claims

- Not staging load test  
- Not cutover / process_split / d3_production authorize  
