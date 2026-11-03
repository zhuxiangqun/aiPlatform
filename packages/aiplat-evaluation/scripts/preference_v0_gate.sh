#!/usr/bin/env bash
# Preference v0 gate — solo engineering fixture by default (≠ human κ / accuracy).
# Pass AIPLAT_EVAL_PREF_A / AIPLAT_EVAL_PREF_B for real worksheets.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PAIRS="${AIPLAT_EVAL_PREF_PAIRS:-$ROOT/docs/a3/preference_pairs.v0.json}"
A_SHEET="${AIPLAT_EVAL_PREF_A:-$ROOT/docs/a3/fixtures/preference_solo_fixture.json}"
B_SHEET="${AIPLAT_EVAL_PREF_B:-}"
EVID_DIR="${AIPLAT_EVAL_PREF_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${AIPLAT_EVAL_PREF_OUT:-$EVID_DIR/local-eval-preference-v0-${STAMP}.json}"

echo "== unit: preference v0 =="
PYTHONPATH=. python3 -m pytest tests/test_preference_v0.py -q --tb=line

echo "== preference report (fixture solo unless AIPLAT_EVAL_PREF_A set) =="
ARGS=(--pairs "$PAIRS" --a "$A_SHEET" --out "$OUT")
if [[ -n "$B_SHEET" ]]; then
  ARGS+=(--b "$B_SHEET")
fi
PYTHONPATH=. python3 "$ROOT/scripts/preference_v0_report.py" "${ARGS[@]}"

python3 - <<PY
import json
from pathlib import Path
p = Path("$OUT")
d = json.loads(p.read_text(encoding="utf-8"))
assert d.get("accuracy_claim") is False
cov = float((d.get("annotator_a") or {}).get("coverage") or 0)
assert cov >= 0.95, f"coverage too low: {cov}"
# Fixture path must not claim inter-annotator human κ as accuracy.
assert d.get("not_accuracy_certification") is True
print(json.dumps({
    "gate": "ok",
    "coverage_a": cov,
    "inter_agreement": (d.get("inter_annotator") or {}).get("agreement"),
    "evidence": str(p),
    "accuracy_claim": False,
}, ensure_ascii=False))
PY

echo "preference v0 gate PASS (accuracy_claim=false; fixture≠human κ)"
