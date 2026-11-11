---
doc_type: Reference
---

# G2b send checklist

1. Edit **`model_outputs.json`** only (flat `{task_id: answer}`).
   Do **not** hand-paste multi-line answers into `g2b_facilitator.json`.
2. Sync:

```bash
python3 packages/aiplat-evaluation/scripts/human_worksheet_pack.py \
  --from-outputs /Users/apple/workdata/person/zy/aiPlatform/packages/aiplat-evaluation/docs/a3/human_pack/20261104T063000Z-n100
```

- **Send to annotators**: `g2b_annotator_a.json`, `g2b_annotator_b.json` only
- **Keep private**: `g2b_facilitator.json` / `model_outputs.json` (gold hints)
- After fill: `scripts/g2b_kappa.py --a … --b … --tasks docs/a3/g2b_tasks.v0.json`
