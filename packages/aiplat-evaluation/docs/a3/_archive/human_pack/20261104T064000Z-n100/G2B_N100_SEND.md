---
doc_type: Reference
---

# G2b n=100 expand — send sheet

1. Confirm `model_outputs.json` has 100 non-empty answers (run with `G2B_RUN_MODEL=1` if needed).
2. Send **only** `g2b_annotator_a.json` / `g2b_annotator_b.json` to two distinct humans.
3. They must fill `pass` for **g2b-31..g2b-100** (01–30 already seeded from prior dual-human evidence).
4. Blind: no gold_pass_hint, no sharing between A/B.
5. After both return, run κ + accuracy closeout (see `docs/a3/G2B_N100.md`).
6. `accuracy_claim` stays **false** until product-owner attestation.
