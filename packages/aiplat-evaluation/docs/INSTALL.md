# Evaluation — D1 Thin (co-hosted)

> Deploy unit: **central** · Hosted by **aiplat** · No A3 process/DB split.

```bash
export AIPLAT_HOME=/tmp/aiplat-eval-d1-demo
export AIPLAT_EVAL_PREFIX=$AIPLAT_HOME/evaluation
bash packages/aiplat-evaluation/scripts/d1_install.sh --smoke
```

Smoke asserts:

- module contract samples (protocol + healthz)
- `GET /api/core/eval/healthz` → `product_id=evaluation`
- `to_eval_protocol_v0` adapter shape
