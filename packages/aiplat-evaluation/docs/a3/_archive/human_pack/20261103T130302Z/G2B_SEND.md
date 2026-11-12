---
doc_type: Reference
---

# G2b send checklist

- **Send to annotators**: `g2b_annotator_a.json`, `g2b_annotator_b.json` only
- **Keep private**: `g2b_facilitator.json` (has `gold_pass_hint`)
- After fill: `scripts/g2b_kappa.py --a … --b … --tasks docs/a3/g2b_tasks.v0.json`
