#!/usr/bin/env bash
# Gate3 Pi Thin pilot — smoke in an isolated env (ADR-08 / GATE3_PI_THIN_PILOT.md).
# Does not start platform/core control plane. Exits non-zero if AIPLAT_ENTERPRISE=1.
#
# GATE3_PI_THIN_PHASE=a (default): stub smoke against fixtures/sample-app
# GATE3_PI_THIN_PHASE=b: export_pi_bundle → smoke + AIPLAT_SLICE_EVIDENCE assert
# GATE3_PI_THIN_PHASE=c: b → ingest_slice_evidence_from_jsonl → diagnosis report
# GATE3_PI_THIN_PHASE=d: c → FDE slice signoff bind report_id (SCENE F1)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${GATE3_PI_THIN_ENV:-$ROOT/.env.gate3-pi-thin}"
EXAMPLE="$SCRIPT_DIR/gate3_pi_thin.env.example"
PHASE="${GATE3_PI_THIN_PHASE:-a}"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$EXAMPLE" ]]; then
    echo "NOTE: $ENV_FILE missing — loading example defaults from $EXAMPLE"
    ENV_FILE="$EXAMPLE"
  else
    echo "ERROR: missing $ENV_FILE and $EXAMPLE" >&2
    exit 2
  fi
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ "${AIPLAT_ENTERPRISE:-0}" == "1" ]]; then
  echo "ERROR: Gate3 Pi Thin pilot must not run with AIPLAT_ENTERPRISE=1 (control-plane bleed)." >&2
  exit 3
fi

export AIPLAT_HTTP_STUB="${AIPLAT_HTTP_STUB:-1}"
export AIPLAT_HTTP_PORT="${AIPLAT_HTTP_PORT:-18787}"
export AIPLAT_HTTP_API_KEY="${AIPLAT_HTTP_API_KEY:-gate3-pi-thin-pilot-key}"

run_phase_b() {
  local SAMPLE="${GATE3_PI_THIN_SAMPLE:-$ROOT/fixtures/sample-app}"
  local EXPORT_DIR="${GATE3_PI_THIN_EXPORT:-/tmp/aiplat-gate3-export-sample}"
  EVIDENCE_PATH="${AIPLAT_SLICE_EVIDENCE_PATH:-/tmp/aiplat-gate3-phase-b-evidence.jsonl}"
  mkdir -p "$EXPORT_DIR" "$(dirname "$EVIDENCE_PATH")"
  rm -f "$EVIDENCE_PATH"
  echo "Gate3 Phase B: export_pi_bundle $SAMPLE → $EXPORT_DIR"
  python3 "$REPO/scripts/export_pi_bundle.py" --app-home "$SAMPLE" --out "$EXPORT_DIR"
  export AIPLAT_APP_HOME="$EXPORT_DIR"
  export AIPLAT_SLICE_EVIDENCE=1
  export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
  export AIPLAT_SLICE_SCENARIO_ID="${AIPLAT_SLICE_SCENARIO_ID:-fp-customer-lock-service-bundle-pi-diag-001}"
  export AIPLAT_SLICE_BUNDLE_VERSION="${AIPLAT_SLICE_BUNDLE_VERSION:-gate3-phase-b}"
  export AIPLAT_SLICE_RUNTIME_VERSION="${AIPLAT_SLICE_RUNTIME_VERSION:-pi-thin-gate3-b}"
  echo "Gate3 Pi Thin pilot phase=b stub=$AIPLAT_HTTP_STUB port=$AIPLAT_HTTP_PORT app=$AIPLAT_APP_HOME evidence=$EVIDENCE_PATH"
  bash "$ROOT/scripts/http_smoke.sh"
  if [[ ! -s "$EVIDENCE_PATH" ]]; then
    echo "ERROR: Phase B evidence file missing or empty: $EVIDENCE_PATH" >&2
    return 4
  fi
  if ! grep -q 'fp-customer-lock-service-bundle-pi-diag-001' "$EVIDENCE_PATH"; then
    echo "ERROR: Phase B evidence missing scenario_id" >&2
    return 5
  fi
  if ! grep -q 'http_chat' "$EVIDENCE_PATH"; then
    echo "ERROR: Phase B evidence missing http_chat event" >&2
    return 6
  fi
  echo "PASS: Gate3 Phase B (exported bundle + slice evidence)"
  return 0
}

run_phase_c_python() {
  PYTHONPATH="${REPO}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import json
import os
import sys

from core.apps.fde.service.slice_evidence import (
    build_slice_diagnosis_report,
    ingest_slice_evidence_from_jsonl,
)

path = os.environ["AIPLAT_SLICE_EVIDENCE_PATH"]
sid = os.environ.get("AIPLAT_SLICE_SCENARIO_ID", "fp-customer-lock-service-bundle-pi-diag-001")
ing = ingest_slice_evidence_from_jsonl(path=path, scenario_id=sid, aiplat_reachable=True)
if not ing.get("ok"):
    print("ERROR: ingest failed:", json.dumps(ing, ensure_ascii=False), file=sys.stderr)
    sys.exit(7)
rep = build_slice_diagnosis_report(scenario_id=sid, ingest_id=ing["ingest_id"])
if not rep.get("ok"):
    print("ERROR: report failed:", json.dumps(rep, ensure_ascii=False), file=sys.stderr)
    sys.exit(8)
if rep.get("status") != "ok" or not rep.get("diagnosis_ok"):
    print("ERROR: diagnosis not ok:", json.dumps(rep, ensure_ascii=False), file=sys.stderr)
    sys.exit(9)
rid = rep.get("report_id")
print(
    "PASS: Gate3 Phase C ingest_id=%s report_id=%s status=%s"
    % (ing.get("ingest_id"), rid, rep.get("status"))
)
print("REPORT_ID=%s" % rid)
PY
}

if [[ "$PHASE" == "b" || "$PHASE" == "B" ]]; then
  run_phase_b
  exit $?
fi

if [[ "$PHASE" == "c" || "$PHASE" == "C" ]]; then
  export AIPLAT_HOME="${GATE3_PI_THIN_AIPLAT_HOME:-/tmp/aiplat-gate3-phase-c-home}"
  mkdir -p "$AIPLAT_HOME"
  EVIDENCE_PATH="${AIPLAT_SLICE_EVIDENCE_PATH:-/tmp/aiplat-gate3-phase-c-evidence.jsonl}"
  export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
  run_phase_b
  echo "Gate3 Phase C: ingest JSONL → diagnosis MVP ($EVIDENCE_PATH)"
  run_phase_c_python
  exit $?
fi

if [[ "$PHASE" == "d" || "$PHASE" == "D" ]]; then
  export AIPLAT_HOME="${GATE3_PI_THIN_AIPLAT_HOME:-/tmp/aiplat-gate3-phase-d-home}"
  mkdir -p "$AIPLAT_HOME"
  EVIDENCE_PATH="${AIPLAT_SLICE_EVIDENCE_PATH:-/tmp/aiplat-gate3-phase-d-evidence.jsonl}"
  export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
  run_phase_b
  echo "Gate3 Phase D: Phase C then FDE signoff bind report_id"
  C_OUT="$(run_phase_c_python)"
  echo "$C_OUT"
  REPORT_ID="$(printf '%s\n' "$C_OUT" | awk -F= '/^REPORT_ID=/{print $2}' | tail -1)"
  if [[ -z "$REPORT_ID" ]]; then
    echo "ERROR: Phase D missing REPORT_ID from Phase C" >&2
    exit 10
  fi
  export GATE3_PHASE_D_REPORT_ID="$REPORT_ID"
  PYTHONPATH="${REPO}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import json
import os
import sys
import time
from pathlib import Path

from core.apps.fde.service.slice_evidence import validate_slice_signoff_reports

sid = os.environ.get("AIPLAT_SLICE_SCENARIO_ID", "fp-customer-lock-service-bundle-pi-diag-001")
rid = os.environ["GATE3_PHASE_D_REPORT_ID"]
home = Path(os.environ["AIPLAT_HOME"])

neg = validate_slice_signoff_reports({"scenario_id": sid, "for_slice": True})
if neg.get("ok"):
    print("ERROR: expected signoff without report_id to fail", json.dumps(neg), file=sys.stderr)
    sys.exit(11)

pos = validate_slice_signoff_reports(
    {
        "scenario_id": sid,
        "for_slice": True,
        "evidence_report_ids": [rid],
    }
)
if not pos.get("ok"):
    print("ERROR: signoff with report_id failed:", json.dumps(pos, ensure_ascii=False), file=sys.stderr)
    sys.exit(12)

acc_dir = home / "five_products_slice" / "acceptance"
acc_dir.mkdir(parents=True, exist_ok=True)
fid = "%s-%d" % (sid, int(time.time()))
record = {
    "ok": True,
    "phase": "gate3-d",
    "scenario_id": sid,
    "spec_id": sid,
    "acceptance_decision": "accepted",
    "evidence_report_ids": list(pos.get("report_ids") or [rid]),
    "for_slice": True,
    "signed_by": "gate3-phase-d-pilot",
    "notes": "sandbox bind record (no HTTP preflight); SCENE F1",
    "record_id": fid,
}
path = acc_dir / ("%s.json" % fid)
path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("PASS: Gate3 Phase D bound report_id=%s record=%s" % (rid, path))
PY
  exit $?
fi

if [[ -z "${AIPLAT_APP_HOME:-}" ]]; then
  export AIPLAT_APP_HOME="$ROOT/fixtures/sample-app"
fi

echo "Gate3 Pi Thin pilot phase=a stub=$AIPLAT_HTTP_STUB port=$AIPLAT_HTTP_PORT app=$AIPLAT_APP_HOME enterprise=${AIPLAT_ENTERPRISE:-0}"
exec bash "$ROOT/scripts/http_smoke.sh"
