# Ontology — D1 Thin (co-hosted)

> Deploy unit: **central** · Hosted by **aiplat** · No A3 process split.

```bash
export AIPLAT_HOME=/tmp/aiplat-ontology-d1-demo
export AIPLAT_ONTOLOGY_PREFIX=$AIPLAT_HOME/ontology
bash packages/aiplat-ontology/scripts/d1_install.sh --smoke
```

Smoke asserts:

- module contract samples
- `GET /api/core/ontology/healthz` → `product_id=ontology`
- `GET /api/core/wiki/pages` includes `ontology_api`
