---
doc_type: Reference
---

# G2b re-review / correction procedure (living)

> Parent protocol (archived): [`_archive/G2B_100_PROTOCOL.md`](./_archive/G2B_100_PROTOCOL.md)  
> Closeout index: [`G2B_ACCURACY_CLOSEOUT.md`](./G2B_ACCURACY_CLOSEOUT.md)  
> Honesty: κ ≠ accuracy · product `accuracy_claim=false` · this procedure does **not** unlock accuracy claims

## Why this exists

The signed G2b protocol freezes labels after sign-off and forbids post-hoc threshold fishing. Real rubric errors still need a **pre-registered** correction path so a re-review is not confused with fishing.

## Allowed triggers

| Trigger | Allowed? |
|---------|----------|
| Annotator / facilitator finds a clear rubric mislabel (wrong expected, swapped id, transcription error) | ✅ |
| Model output changed after freeze (prompt/model/code drift) | ❌ — new protocol run required |
| Moving a borderline fail→pass solely to clear a numeric threshold | ❌ |

## Procedure

1. **Open a correction ticket** under `.aiplat/eval_trust/` (or append to the adjudication JSON) with: case id, original label, proposed label, evidence quote, proposer, date.
2. **Second annotator** (or facilitator if dual-human already closed) independently confirms or rejects — same dual-human honesty as original G2b.
3. **Batch commit**: only after confirmation, update the adjudication artifact; bump a `re_review_revision` integer; never silently edit the signed protocol PDF/MD.
4. **Recompute** κ / pass_rate / Wilson CI from the revised labels; record both pre- and post-correction metrics in closeout notes.
5. **Claim lock**: product `accuracy_claim` stays false unless a separate unlock gate passes; scoped claims must cite the revision id.

## 2026-11-13 instance

Closeout re-review that lifted pass_rate 0.72→0.80 is **in-scope for this procedure** only if dual confirmation + revision id are recorded on the adjudication artifact. Treat undocumented threshold-crossing edits as process debt, not as a template for future unlocks.
