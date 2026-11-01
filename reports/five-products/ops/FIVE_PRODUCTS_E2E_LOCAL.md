# Five-products cross-capability E2E (local)

- recorded_at: `20261101T032316Z`
- environment: `local`
- result: **PASS**
- evidence: `ops/evidence/local-five-products-e2e-20261101T032316Z.json`
- production_signed: **false**
- staging_ready: **false**

## Flow covered

1. STATUS ↔ manifest  
2. Packaging + perf + A2/compat  
3. `slice_e2e` lock-service（Bundle → Pi Thin → FDE acceptance bind）  
4. `slice_e2e --inject disconnect` fail-closed  
5. Ontology / Evaluation / FDE D1 smoke  
6. 四轨 authorize **REFUSE**

## Commands

```bash
bash scripts/ops_five_products_e2e_local.sh
```

## Unfreeze

[`ENGINEERING_UNFREEZE_D3_E2E.md`](./ENGINEERING_UNFREEZE_D3_E2E.md) — authorize 仍冻结。
