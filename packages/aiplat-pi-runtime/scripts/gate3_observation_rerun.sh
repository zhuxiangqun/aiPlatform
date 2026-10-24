#!/usr/bin/env bash
# Gate3 observation window re-run helper (G3-OBS2 / G3-OBS3).
# Default: phase=a + phase=d (same as kickoff/end drill).
# Optional: GATE3_OBS_INCLUDE_EF=1 also runs phase=e and phase=f.
# Does not rewrite ROLLBACK.md — paste PASS lines into the drill record.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PILOT="$ROOT/scripts/gate3_pi_thin_pilot.sh"
LABEL="${GATE3_OBS_LABEL:-observation-rerun}"

unset AIPLAT_ACCEPTANCE_DIR || true
# Keep AIPLAT_HOME unset so each phase uses its default sandbox home.

run_phase() {
  local p="$1"
  echo "======== Gate3 observation ($LABEL) PHASE=$p ========"
  GATE3_PI_THIN_PHASE="$p" bash "$PILOT"
}

run_phase a
run_phase d

if [[ "${GATE3_OBS_INCLUDE_EF:-0}" == "1" ]]; then
  run_phase e
  run_phase f
fi

echo "PASS: Gate3 observation re-run label=$LABEL (a+d${GATE3_OBS_INCLUDE_EF:+ +e+f if set})"
