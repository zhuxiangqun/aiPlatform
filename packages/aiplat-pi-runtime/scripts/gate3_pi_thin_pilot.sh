#!/usr/bin/env bash
# Gate3 Pi Thin pilot — smoke in an isolated env (ADR-08 / GATE3_PI_THIN_PILOT.md).
# Does not start platform/core control plane. Exits non-zero if AIPLAT_ENTERPRISE=1.
#
# GATE3_PI_THIN_PHASE=a (default): stub smoke against fixtures/sample-app
# GATE3_PI_THIN_PHASE=b: export_pi_bundle → smoke + AIPLAT_SLICE_EVIDENCE assert (Phase B)
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

if [[ "$PHASE" == "b" || "$PHASE" == "B" ]]; then
  SAMPLE="${GATE3_PI_THIN_SAMPLE:-$ROOT/fixtures/sample-app}"
  EXPORT_DIR="${GATE3_PI_THIN_EXPORT:-/tmp/aiplat-gate3-export-sample}"
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
    exit 4
  fi
  if ! grep -q 'fp-customer-lock-service-bundle-pi-diag-001' "$EVIDENCE_PATH"; then
    echo "ERROR: Phase B evidence missing scenario_id" >&2
    exit 5
  fi
  if ! grep -q 'http_chat' "$EVIDENCE_PATH"; then
    echo "ERROR: Phase B evidence missing http_chat event" >&2
    exit 6
  fi
  echo "PASS: Gate3 Phase B (exported bundle + slice evidence)"
  exit 0
fi

if [[ -z "${AIPLAT_APP_HOME:-}" ]]; then
  export AIPLAT_APP_HOME="$ROOT/fixtures/sample-app"
fi

echo "Gate3 Pi Thin pilot phase=a stub=$AIPLAT_HTTP_STUB port=$AIPLAT_HTTP_PORT app=$AIPLAT_APP_HOME enterprise=${AIPLAT_ENTERPRISE:-0}"
exec bash "$ROOT/scripts/http_smoke.sh"
