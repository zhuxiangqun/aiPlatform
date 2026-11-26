---
doc_type: Reference
---

# Central / Edge compatibility matrix (D2 Thin)

> Packaging-only D2 slice. Not a full admin/security pack.  
> Matrix: [`../compat/matrix.yaml`](../compat/matrix.yaml)

## Check

```bash
bash packages/aiplat-central/scripts/d2_compat_check.sh
```

Validates:

- package / version / healthz schema / smoke script paths exist
- `package.json` version ≥ `min_version`
- healthz schema `product_id` const matches unit
- shared contracts (`ontology.api.v0`, `eval.protocol.v0`, `aiplat.control.v0`) present

## Forbidden without ADR

Listed under `forbidden_without_adr` in the matrix (PG/HA, full five-process split, Field 卷/DB 长驻 Draft 等)。  
FDE **薄** optional compose 长驻已由 `ADR-FDE-COMPOSE-LONG-RUNNING` Accepted（F11）覆盖；Field `compose.field-longrunning` 仍禁。
