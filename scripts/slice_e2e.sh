#!/usr/bin/env bash
# Clean-env five-products slice E2E (replaces synthetic five_products_slice_smoke).
#
#   bash scripts/slice_e2e.sh --scenario lock-service
#   bash scripts/slice_e2e.sh --scenario lock-service --inject disconnect
#
# - Clean AIPLAT_HOME under tmp/ (no ~/.aiplat, no reports/ writes)
# - Live Gate3 Pi Thin process + JSONL evidence (HTTP stub allowed)
# - --inject disconnect → diagnosis status must NOT be ok (fail-closed);
#   never runs Phase E (no accepted under acceptance/)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$REPO/packages/aiplat-pi-runtime"
SCENARIO="lock-service"
INJECT=""
OUT_ROOT="${SLICE_E2E_OUT:-$REPO/tmp/slice-e2e}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario) SCENARIO="${2:-}"; shift 2 ;;
    --inject) INJECT="${2:-}"; shift 2 ;;
    --out) OUT_ROOT="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ "$SCENARIO" != "lock-service" ]]; then
  echo "ERROR: only --scenario lock-service supported" >&2
  exit 2
fi
case "$INJECT" in
  ""|disconnect) ;;
  *) echo "ERROR: --inject must be empty or disconnect" >&2; exit 2 ;;
esac

RUN_DIR="$OUT_ROOT/$STAMP${INJECT:+-$INJECT}"
HOME_DIR="$RUN_DIR/aiplat-home"
EVIDENCE_PATH="$RUN_DIR/evidence.jsonl"
EXPORT_DIR="$RUN_DIR/export"
SAMPLE_DIR="$RUN_DIR/lock-service-sample"
mkdir -p "$RUN_DIR" "$HOME_DIR" "$EXPORT_DIR"
rm -f "$EVIDENCE_PATH"

export AIPLAT_HOME="$HOME_DIR"
export AIPLAT_ENTERPRISE=0
export GATE3_PI_THIN_AIPLAT_HOME="$HOME_DIR"
export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
export AIPLAT_SLICE_SCENARIO_ID="fp-customer-lock-service-bundle-pi-diag-001"
export AIPLAT_SLICE_BUNDLE_VERSION="slice-e2e-$STAMP"
export AIPLAT_SLICE_RUNTIME_VERSION="pi-thin-slice-e2e"
export GATE3_PI_THIN_EXPORT="$EXPORT_DIR"
export GATE3_PI_THIN_SAMPLE="$SAMPLE_DIR"
export GATE3_PI_THIN_ENV="${GATE3_PI_THIN_ENV:-$RUNTIME/scripts/gate3_pi_thin.env.example}"
export SLICE_E2E_RUN_DIR="$RUN_DIR"

echo "slice_e2e: out=$RUN_DIR scenario=$SCENARIO inject=${INJECT:-none}"

run_gate3() {
  local phase="$1"
  (
    cd "$RUNTIME"
    GATE3_PI_THIN_PHASE="$phase" \
      GATE3_PI_THIN_AIPLAT_HOME="$HOME_DIR" \
      AIPLAT_HOME="$HOME_DIR" \
      AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH" \
      AIPLAT_SLICE_SCENARIO_ID="$AIPLAT_SLICE_SCENARIO_ID" \
      AIPLAT_SLICE_BUNDLE_VERSION="$AIPLAT_SLICE_BUNDLE_VERSION" \
      AIPLAT_SLICE_RUNTIME_VERSION="$AIPLAT_SLICE_RUNTIME_VERSION" \
      GATE3_PI_THIN_EXPORT="$EXPORT_DIR" \
      GATE3_PI_THIN_SAMPLE="$SAMPLE_DIR" \
      GATE3_PI_THIN_ENV="$GATE3_PI_THIN_ENV" \
      GATE3_PI_THIN_LOCK_SAMPLE="${GATE3_PI_THIN_LOCK_SAMPLE:-0}" \
      bash scripts/gate3_pi_thin_pilot.sh
  )
}

if [[ -z "$INJECT" ]]; then
  run_gate3 e | tee "$RUN_DIR/gate3.log"
  if [[ ! -s "$EVIDENCE_PATH" ]]; then
    echo "ERROR: missing live evidence JSONL: $EVIDENCE_PATH" >&2
    exit 4
  fi
  if ! grep -q 'http_chat' "$EVIDENCE_PATH"; then
    echo "ERROR: evidence not live (no http_chat event)" >&2
    exit 5
  fi
  # Refuse synthetic smoke markers in this path
  if grep -q 'smoke_ok\|accepted (smoke)\|synthetic Pi run' "$RUN_DIR/gate3.log" "$EVIDENCE_PATH" 2>/dev/null; then
    echo "ERROR: synthetic smoke markers found" >&2
    exit 6
  fi
  echo "PASS: slice_e2e positive (Gate3 E live evidence → report → signoff bind)"
  echo "OUT=$RUN_DIR"
  exit 0
fi

# --- disconnect inject ---
# Materialize lock-service + Phase B only (evidence JSONL). Do NOT run Phase E
# (which writes acceptance_decision=accepted into the same HOME).
# Diagnose on a clean AIPLAT_HOME with assumed_reachable=False.
set +e
GATE3_PI_THIN_LOCK_SAMPLE=1 run_gate3 b >"$RUN_DIR/gate3.log" 2>&1
set -e
if [[ ! -s "$EVIDENCE_PATH" ]]; then
  echo "ERROR: no evidence for disconnect inject; see $RUN_DIR/gate3.log" >&2
  exit 7
fi
if ! grep -q 'http_chat' "$EVIDENCE_PATH"; then
  echo "ERROR: disconnect evidence not live (no http_chat); see $RUN_DIR/gate3.log" >&2
  exit 7
fi
if [[ -f "$EXPORT_DIR/agent_manifest.json" ]] && ! grep -q 'lock-service' "$EXPORT_DIR/agent_manifest.json"; then
  echo "ERROR: disconnect path must use lock-service sample (got non-lock export)" >&2
  exit 7
fi

# Fresh home for diagnosis — never reuse a home that Phase E may have tainted.
DIAG_HOME="$RUN_DIR/aiplat-home-disconnect"
mkdir -p "$DIAG_HOME"
rm -rf "$DIAG_HOME/five_products_slice"

PYTHONPATH="${REPO}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}" \
AIPLAT_HOME="$DIAG_HOME" \
AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH" \
AIPLAT_SLICE_SCENARIO_ID="$AIPLAT_SLICE_SCENARIO_ID" \
SLICE_E2E_RUN_DIR="$RUN_DIR" \
python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

from core.apps.fde.service.slice_evidence import (
    build_slice_diagnosis_report,
    ingest_slice_evidence_from_jsonl,
    validate_slice_signoff_reports,
)

path = os.environ["AIPLAT_SLICE_EVIDENCE_PATH"]
sid = os.environ["AIPLAT_SLICE_SCENARIO_ID"]
out = Path(os.environ["SLICE_E2E_RUN_DIR"])
home = Path(os.environ["AIPLAT_HOME"])

ing = ingest_slice_evidence_from_jsonl(
    path=path, scenario_id=sid, assumed_reachable=False
)
if not ing.get("ok"):
    print("ERROR: disconnect ingest failed", ing, file=sys.stderr)
    sys.exit(8)

rep = build_slice_diagnosis_report(
    scenario_id=sid, ingest_id=ing["ingest_id"], assumed_reachable=False
)
(out / "disconnect_report.json").write_text(
    json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8"
)
status = rep.get("status")
diag_ok = bool(rep.get("diagnosis_ok"))
if status == "ok" or diag_ok:
    print("ERROR: disconnect must not yield ok diagnosis", rep, file=sys.stderr)
    sys.exit(9)

# Explicit non-acceptance decision (never write accepted)
decision = {
    "decision": "rejected",
    "reason": "assumed_unreachable_disconnect_inject",
    "report_id": rep.get("report_id"),
    "status": status,
}
(out / "ACCEPTANCE.json").write_text(
    json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
)
if decision["decision"] == "accepted":
    print("ERROR: must not accept under disconnect", file=sys.stderr)
    sys.exit(10)

# Signoff must refuse stale/unreachable reports (not merely bind report_id)
gate = validate_slice_signoff_reports(
    {"scenario_id": sid, "evidence_report_ids": [rep.get("report_id")]}
)
(out / "signoff_gate.json").write_text(
    json.dumps({"gate": gate, "diagnosis_status": status}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
if gate.get("ok"):
    print("ERROR: signoff gate must fail for disconnect report", gate, file=sys.stderr)
    sys.exit(11)
if gate.get("error") != "diagnosis_not_ok":
    print("ERROR: expected diagnosis_not_ok", gate, file=sys.stderr)
    sys.exit(12)

# Hard assert: no acceptance_decision=accepted anywhere under the run dir
accepted_hits = []
for p in out.rglob("*.json"):
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        continue
    if '"accepted"' not in text and "'accepted'" not in text:
        continue
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        continue
    blob = json.dumps(data, ensure_ascii=False)
    if '"acceptance_decision": "accepted"' in blob or '"decision": "accepted"' in blob:
        accepted_hits.append(str(p.relative_to(out)))
if accepted_hits:
    print("ERROR: disconnect run must not contain accepted records:", accepted_hits, file=sys.stderr)
    sys.exit(13)

acc_roots = [
    home / "five_products_slice" / "acceptance",
    out / "aiplat-home" / "five_products_slice" / "acceptance",
]
for acc in acc_roots:
    if not acc.is_dir():
        continue
    for p in acc.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("acceptance_decision") == "accepted" or data.get("decision") == "accepted":
            print("ERROR: found accepted under", p, file=sys.stderr)
            sys.exit(14)

print(
    "PASS: slice_e2e disconnect fail-closed status=%s diagnosis_ok=%s decision=rejected "
    "signoff_ok=False no_accepted=True"
    % (status, diag_ok)
)
print("REPORT_ID=%s" % rep.get("report_id"))
PY

echo "OUT=$RUN_DIR"
