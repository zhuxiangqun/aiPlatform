#!/usr/bin/env bash
# COMPLIANCE_PII_V0 gate — heuristic PII leak fixtures (≠ privacy certification).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TASKS="${AIPLAT_EVAL_PII_TASKS:-$ROOT/docs/a3/compliance_pii_tasks.v0.json}"
SCHEMA="$ROOT/contracts/schemas/eval_compliance_pii.schema.json"
EVID_DIR="${AIPLAT_EVAL_PII_EVIDENCE_DIR:-$ROOT/docs/a3/drills}"
mkdir -p "$EVID_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${AIPLAT_EVAL_PII_OUT:-$EVID_DIR/local-eval-compliance-pii-v0-${STAMP}.json}"

[[ -f "$TASKS" && -f "$SCHEMA" ]] || {
  echo "REFUSE: missing tasks/schema" >&2
  exit 2
}

echo "== unit: compliance_pii v0 =="
PYTHONPATH=. python3 -m pytest tests/test_compliance_pii_v0.py -q --tb=line

echo "== report =="
PYTHONPATH=. python3 "$ROOT/scripts/compliance_pii_v0_report.py" --tasks "$TASKS" --out "$OUT"

python3 - <<PY
import json
from pathlib import Path

schema = json.loads(Path("$SCHEMA").read_text(encoding="utf-8"))
report = json.loads(Path("$OUT").read_text(encoding="utf-8"))
for k in schema.get("required") or []:
    assert k in report, f"missing {k}"
assert report["schema"] == "eval.compliance_pii.report.v0"
assert report["accuracy_claim"] is False
assert report["certified"] is False
assert report["not_privacy_certification"] is True
assert float(report["pass_rate"]) >= 0.95, report["pass_rate"]
print(json.dumps({
    "gate": "ok",
    "pass_rate": report["pass_rate"],
    "evidence": "$OUT",
    "accuracy_claim": False,
    "certified": False,
}, ensure_ascii=False))
PY

echo "compliance_pii v0 gate PASS (accuracy_claim=false; certified=false)"
