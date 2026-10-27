#!/usr/bin/env bash
# ADR-10 diagnosis MVP pilot — isolated AIPLAT_HOME smoke (Phase A–D).
# Reuses ingest_slice_evidence_from_jsonl + build_slice_diagnosis_report.
# Phase D D1: AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 requires ADR10_ALLOW_USER_HOME=1
# and AIPLAT_HOME under $HOME (default $HOME/.aiplat/adr10-diagnosis-mvp-d1).
# Not D2 platform route binding. Not E4 / ADR-09.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${ADR10_DIAG_ENV:-$REPO/.env.adr10-diagnosis-mvp}"
EXAMPLE="$SCRIPT_DIR/adr10_diagnosis_mvp.env.example"

resolve_python() {
  if [[ -n "${ADR10_DIAG_PYTHON:-}" ]]; then
    echo "$ADR10_DIAG_PYTHON"
  elif [[ -x "$REPO/.venv/bin/python" ]]; then
    echo "$REPO/.venv/bin/python"
  else
    echo "python3"
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$EXAMPLE" ]]; then
    echo "NOTE: $ENV_FILE missing — loading example defaults from $EXAMPLE"
    ENV_FILE="$EXAMPLE"
  else
    echo "ERROR: missing $ENV_FILE and $EXAMPLE" >&2
    exit 2
  fi
fi

# Preserve caller-exported home across env-file source (Phase C isolates runs).
_CALLER_DIAG_HOME="${ADR10_DIAG_AIPLAT_HOME:-}"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -n "$_CALLER_DIAG_HOME" ]]; then
  ADR10_DIAG_AIPLAT_HOME="$_CALLER_DIAG_HOME"
fi

# BOUNDARY B (ADR-09 step4): ADR10_DIAGNOSIS_MVP_SPLIT=1 → canonical diagnosis-mvp home.
# Explicit caller ADR10_DIAG_AIPLAT_HOME wins; env.example legacy home is ignored.
# Still one-shot; not compose long-running.
if [[ "${ADR10_DIAGNOSIS_MVP_SPLIT:-0}" == "1" ]]; then
  if [[ -n "$_CALLER_DIAG_HOME" ]]; then
    ADR10_DIAG_AIPLAT_HOME="$_CALLER_DIAG_HOME"
  elif [[ "${ADR10_ALLOW_USER_HOME:-0}" == "1" ]]; then
    ADR10_DIAG_AIPLAT_HOME="${HOME}/.aiplat/diagnosis-mvp"
  else
    ADR10_DIAG_AIPLAT_HOME="/tmp/aiplat-diagnosis-mvp"
  fi
fi

HOME_DIR="${ADR10_DIAG_AIPLAT_HOME:-/tmp/aiplat-adr10-diag-home}"
# Resolve ~ for comparisons
HOME_DIR="${HOME_DIR/#\~/$HOME}"

if [[ "${AIPLAT_DIAGNOSIS_PROD_DEFAULT:-0}" == "1" ]]; then
  # Phase D D1: dual opt-in only — bare PROD_DEFAULT=1 still refused (exit 3).
  if [[ "${ADR10_ALLOW_USER_HOME:-0}" != "1" ]]; then
    echo "ERROR: AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 requires ADR10_ALLOW_USER_HOME=1 (Phase D D1)." >&2
    exit 3
  fi
  case "$HOME_DIR" in
    "$HOME"|"$HOME"/*) ;;
    *)
      echo "ERROR: Phase D D1 requires AIPLAT_HOME under \$HOME (got $HOME_DIR)" >&2
      exit 3
      ;;
  esac
elif [[ "$HOME_DIR" == "$HOME/.aiplat" || "$HOME_DIR" == "$HOME/.aiplat"/* || "$HOME_DIR" == "$HOME"/* ]]; then
  if [[ "${ADR10_ALLOW_USER_HOME:-0}" != "1" ]]; then
    echo "ERROR: refuse \$HOME paths without ADR10_ALLOW_USER_HOME=1" >&2
    exit 4
  fi
fi

export AIPLAT_HOME="$HOME_DIR"
mkdir -p "$AIPLAT_HOME"
SID="${AIPLAT_SLICE_SCENARIO_ID:-fp-customer-lock-service-bundle-pi-diag-001}"
EVIDENCE_PATH="${ADR10_DIAG_EVIDENCE_PATH:-$AIPLAT_HOME/pilot-emit.jsonl}"
PY="$(resolve_python)"

cat >"$EVIDENCE_PATH" <<EOF
{"v":1,"type":"emit_open","run_id":"adr10-diag-pilot-1","scenario_id":"$SID","bundle_version":"bv-adr10-a","runtime_version":"diag-mvp-pilot-a","ts":"2026-10-24T00:00:00+00:00"}
{"v":1,"type":"session_start","run_id":"adr10-diag-pilot-1","ts":"2026-10-24T00:00:01+00:00"}
{"v":1,"type":"before_agent_start","run_id":"adr10-diag-pilot-1","ts":"2026-10-24T00:00:02+00:00"}
{"v":1,"type":"http_chat","run_id":"adr10-diag-pilot-1","ts":"2026-10-24T00:00:03+00:00"}
EOF

echo "ADR-10 diagnosis MVP pilot: AIPLAT_HOME=$AIPLAT_HOME scenario=$SID evidence=$EVIDENCE_PATH"

export AIPLAT_SLICE_EVIDENCE_PATH="$EVIDENCE_PATH"
export AIPLAT_SLICE_SCENARIO_ID="$SID"
export ADR10_DIAG_REPO="$REPO"

PYTHONPATH="${REPO}/aiPlat-core${PYTHONPATH:+:$PYTHONPATH}" "$PY" - <<'PY'
import json
import os
import sys

from core.apps.fde.service.slice_evidence import (
    build_slice_diagnosis_report,
    ingest_slice_evidence_from_jsonl,
)

path = os.environ["AIPLAT_SLICE_EVIDENCE_PATH"]
sid = os.environ.get("AIPLAT_SLICE_SCENARIO_ID", "fp-customer-lock-service-bundle-pi-diag-001")
ing = ingest_slice_evidence_from_jsonl(path=path, scenario_id=sid, assumed_reachable=True)
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
print(
    "PASS: ADR-10 diagnosis MVP pilot ingest_id=%s report_id=%s status=%s"
    % (ing.get("ingest_id"), rep.get("report_id"), rep.get("status"))
)
print("REPORT_ID=%s" % rep.get("report_id"))
PY
