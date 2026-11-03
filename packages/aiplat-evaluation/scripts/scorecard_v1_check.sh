#!/usr/bin/env bash
# Validate scorecard_v1.json honesty vs SCORE_SCOPE_V1 + evidence manifest.
# Refuses feature 5 without auditable aggregates + confirmed dual-human attestation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CARD="${AIPLAT_EVAL_SCORECARD:-$ROOT/docs/a3/scorecard_v1.json}"
SCOPE="$ROOT/docs/a3/SCORE_SCOPE_V1.md"
MD="$ROOT/docs/a3/SCORECARD_V1.md"
MANIFEST="${AIPLAT_EVAL_EVIDENCE_MANIFEST:-$ROOT/docs/a3/evidence/evidence_manifest.v1.json}"

[[ -f "$CARD" && -f "$SCOPE" && -f "$MD" ]] || {
  echo "REFUSE: missing scorecard/scope docs" >&2
  exit 2
}
[[ -f "$MANIFEST" ]] || {
  echo "REFUSE: missing evidence manifest: $MANIFEST" >&2
  exit 2
}

export AIPLAT_EVAL_SCORECARD_PATH="$CARD"
export AIPLAT_EVAL_EVIDENCE_MANIFEST_PATH="$MANIFEST"

python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(".").resolve()
card_path = Path(os.environ["AIPLAT_EVAL_SCORECARD_PATH"])
manifest_path = Path(os.environ["AIPLAT_EVAL_EVIDENCE_MANIFEST_PATH"])

card = json.loads(card_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

assert card.get("schema") == "eval.scorecard.v1"
assert card.get("accuracy_claim") is False
assert card.get("process_split_authorized") is False
assert manifest.get("schema") == "eval.scorecard.evidence_manifest.v1"
assert manifest.get("accuracy_claim") is False


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_listed(entries, *, require_present: bool) -> list[str]:
    mismatches: list[str] = []
    for ent in entries or []:
        rel = str(ent.get("path") or "")
        expect = str(ent.get("sha256") or "")
        path = root / rel
        if not path.is_file():
            if require_present or ent.get("required_for_feature_5"):
                mismatches.append(f"missing:{rel}")
            continue
        if not ent.get("verify_when_present", True) and not require_present:
            continue
        got = sha256(path)
        if got != expect:
            mismatches.append(f"sha_mismatch:{rel}")
    return mismatches


agg_bad = check_listed(manifest.get("tracked_aggregates") or [], require_present=True)
assert not agg_bad, f"tracked aggregate evidence failed: {agg_bad}"

# Instruction docs listed in manifest must match when present.
instr_entries = []
for meta in (manifest.get("instruction_versions") or {}).values():
    if isinstance(meta, dict) and meta.get("path") and meta.get("sha256"):
        instr_entries.append(
            {
                "path": meta["path"],
                "sha256": meta["sha256"],
                "verify_when_present": True,
                "required_for_feature_5": True,
            }
        )
instr_bad = check_listed(instr_entries, require_present=True)
assert not instr_bad, f"instruction version hash failed: {instr_bad}"

# Local worksheets: verify only when present (gitignored).
ws_bad = []
for ent in manifest.get("local_worksheets") or []:
    rel = str(ent.get("path") or "")
    path = root / rel
    if not path.is_file():
        continue
    if sha256(path) != str(ent.get("sha256") or ""):
        ws_bad.append(rel)
assert not ws_bad, f"local worksheet sha mismatch: {ws_bad}"

axes = card["axes"]
feat = axes["feature_coverage"]
feat_score = float(feat["score"])
att = manifest.get("dual_human_attestation") or {}
att_status = str(att.get("status") or "").strip().lower()
claimed = att.get("claimed") if isinstance(att.get("claimed"), dict) else {}
att_ok = att_status == "confirmed" and all(
    claimed.get(k) is True
    for k in (
        "two_distinct_humans",
        "independent_blind",
        "not_script_or_ai_generated",
        "not_same_person_both_sides",
    )
)

method = manifest.get("method") or {}
g2b = method.get("g2b") or {}
pref = method.get("preference") or {}

# Load aggregates and cross-check method block.
agg_map = {
    str(e["id"]): root / str(e["path"])
    for e in (manifest.get("tracked_aggregates") or [])
    if e.get("id") and e.get("path")
}
g2b_agg = json.loads(agg_map["g2b_kappa_aggregate"].read_text(encoding="utf-8"))
pref_agg = json.loads(agg_map["preference_aggregate"].read_text(encoding="utf-8"))
assert float(g2b_agg.get("inter_annotator_kappa")) == float(g2b.get("inter_annotator_kappa"))
assert float(g2b_agg.get("agreement")) == float(g2b.get("agreement"))
assert int(g2b_agg.get("n")) == int(g2b.get("n"))
ia = pref_agg.get("inter_annotator") or {}
assert float(ia.get("preference_kappa")) == float(pref.get("preference_kappa"))
assert float(ia.get("agreement")) == float(pref.get("agreement"))
assert int(ia.get("n")) == int(pref.get("n"))

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
    if key in (
        "engineering_architecture",
        "local_independence_no_microvm",
        "feature_coverage",
    ) and score >= 5.0:
        assert card.get("process_split_authorized") is False
        assert card.get("accuracy_claim") is False
        assert card.get("not_production_authorization") is True

if feat_score >= 5.0:
    assert att_ok, (
        "feature_coverage=5 requires dual_human_attestation.status=confirmed "
        "with all claimed booleans true (see docs/a3/EVIDENCE_AUDIT_V1.md)"
    )
    assert bool(feat.get("evidence_audit_ok")) is True, (
        "feature_coverage=5 requires evidence_audit_ok=true"
    )
else:
    # Honesty rollback path while attestation pending / evidence incomplete.
    gaps = feat.get("gaps") or []
    assert "dual_human_attestation_unconfirmed" in gaps or att_ok, (
        "feature <5 without attestation must list gap dual_human_attestation_unconfirmed"
    )

micro = axes["local_independence_with_microvm"]
assert micro.get("eligible_on_darwin") is False
assert micro.get("score") is None

prod = axes["production_independence"]
assert prod.get("scored_in_v1") is False

dims = card.get("dimensions") or []
assert len(dims) >= 6
# Dimensions may still be evidence_ok for local drills; feature axis gate is stricter.
bad = [d["id"] for d in dims if d.get("evidence_ok") is not True]
assert not bad, f"incomplete dimensions: {bad}"

print(
    json.dumps(
        {
            "gate": "ok",
            "feature": feat_score,
            "architecture": axes["engineering_architecture"]["score"],
            "local_no_microvm": axes["local_independence_no_microvm"]["score"],
            "incomplete_dimensions": bad,
            "accuracy_claim": False,
            "evidence_manifest": str(manifest_path.relative_to(root)),
            "dual_human_attestation": att_status,
            "feature_5_allowed": bool(att_ok),
            "local_worksheets_verified": sum(
                1
                for e in (manifest.get("local_worksheets") or [])
                if (root / str(e.get("path") or "")).is_file()
            ),
        },
        ensure_ascii=False,
    )
)
PY

echo "scorecard_v1 check PASS (honesty: evidence manifest + no silent feature 5)"
