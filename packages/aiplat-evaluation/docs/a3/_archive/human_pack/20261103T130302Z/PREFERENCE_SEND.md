---
doc_type: Reference
---

# Preference send checklist

- Send `pref_annotator_a.json` / `pref_annotator_b.json` to two humans
- Each sets `preferred` to `a` | `b` | `tie` (replace null)
- Gate:

```bash
AIPLAT_EVAL_PREF_A=…/pref_annotator_a.json \
AIPLAT_EVAL_PREF_B=…/pref_annotator_b.json \
  bash packages/aiplat-evaluation/scripts/preference_v0_gate.sh
```
