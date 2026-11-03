#!/usr/bin/env bash
# Validate scorecard_v1.json honesty vs SCORE_SCOPE_V1 (no silent 5/5 with gaps).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CARD="${AIPLAT_EVAL_SCORECARD:-$ROOT/docs/a3/scorecard_v1.json}"
SCOPE="$ROOT/docs/a3/SCORE_SCOPE_V1.md"
MD="$ROOT/docs/a3/SCORECARD_V1.md"

[[ -f "$CARD" && -f "$SCOPE" && -f "$MD" ]] || {
  echo "REFUSE: missing scorecard/scope docs" >&2
  exit 2
}

python3 - <<PY
import json
from pathlib import Path

card = json.loads(Path("$CARD").read_text(encoding="utf-8"))
assert card.get("schema") == "eval.scorecard.v1"
assert card.get("accuracy_claim") is False
assert card.get("process_split_authorized") is False

axes = card["axes"]
for key in (
    "feature_coverage",
    "engineering_architecture",
    "local_independence_no_microvm",
):
    ax = axes[key]
    score = float(ax["score"])
    gaps = ax.get("gaps") or []
    eligible = bool(ax.get("full_score_eligible"))
    if score >= 5.0:
        assert eligible and not gaps, f"{key}: score=5 requires eligible and empty gaps"
    if gaps:
        assert score < 5.0, f"{key}: gaps present → score must be <5 (got {score})"
        assert eligible is False, f"{key}: gaps → full_score_eligible must be false"
    if key == "engineering_architecture" and score >= 5.0:
        # Honesty: architecture 5 does not authorize process split or accuracy.
        assert card.get("process_split_authorized") is False
        assert card.get("accuracy_claim") is False

micro = axes["local_independence_with_microvm"]
assert micro.get("eligible_on_darwin") is False
assert micro.get("score") is None

prod = axes["production_independence"]
assert prod.get("scored_in_v1") is False

dims = card.get("dimensions") or []
assert len(dims) >= 6
bad = [d["id"] for d in dims if d.get("evidence_ok") is not True]
# preference/g2b/compliance expected incomplete
assert "compliance_pii_v0" in bad
assert any(d["id"] == "preference_v0" and not d.get("evidence_ok") for d in dims)

print(json.dumps({
    "gate": "ok",
    "feature": axes["feature_coverage"]["score"],
    "architecture": axes["engineering_architecture"]["score"],
    "local_no_microvm": axes["local_independence_no_microvm"]["score"],
    "incomplete_dimensions": bad,
    "accuracy_claim": False,
}, ensure_ascii=False))
PY

echo "scorecard_v1 check PASS (honesty: no silent 5/5 with gaps)"
