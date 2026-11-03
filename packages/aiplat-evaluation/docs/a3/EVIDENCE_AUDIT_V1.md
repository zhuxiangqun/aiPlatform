# Scorecard evidence audit v1

> Honesty: **hashes + aggregates ≠ accuracy** · **dual-human attestation required for feature 5** · raw worksheets stay gitignored

## Problem

`scorecard_v1.json` can claim feature 5 while:

- `docs/a3/human_pack/` and `docs/a3/drills/` are gitignored
- `scorecard_v1_check.sh` only validates JSON fields

That is local self-certification, not repository-auditable 5/5.

## Fix

| Artifact | Tracked? | Role |
|---|---|---|
| [`evidence/evidence_manifest.v1.json`](./evidence/evidence_manifest.v1.json) | ✅ | SHA256 + method + attestation |
| [`evidence/g2b_kappa_aggregate.v1.json`](./evidence/g2b_kappa_aggregate.v1.json) | ✅ | G2b κ aggregate (no raw labels) |
| [`evidence/preference_aggregate.v1.json`](./evidence/preference_aggregate.v1.json) | ✅ | Preference agreement/κ aggregate |
| `human_pack/*.json` | ❌ gitignored | Raw A/B worksheets; hashed in manifest; verified when present locally |

## Gate

```bash
bash packages/aiplat-evaluation/scripts/scorecard_v1_check.sh
```

Refuses feature coverage ≥ 5 unless:

1. Manifest exists and tracked aggregate SHA256 match
2. Aggregate metrics match scorecard claims
3. `dual_human_attestation.status == "confirmed"` with all claimed booleans `true`
4. If local worksheets exist, their SHA256 match the manifest

## Confirm dual humans

Edit `evidence_manifest.v1.json`:

```json
"dual_human_attestation": {
  "status": "confirmed",
  "claimed": {
    "two_distinct_humans": true,
    "independent_blind": true,
    "not_script_or_ai_generated": true,
    "not_same_person_both_sides": true
  },
  "attested_at": "2026-11-04T00:00:00+08:00",
  "attested_by": "<operator-id>"
}
```

Then restore `feature_coverage.score=5.0`, clear gaps, re-run the gate.

If A/B were the same person / script / AI → keep feature ≤ 4.x and redo with two humans.
