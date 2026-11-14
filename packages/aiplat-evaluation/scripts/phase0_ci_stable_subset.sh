#!/usr/bin/env bash
# Phase 0 CI stable subset — scorecard + honesty/architecture pins.
# Does NOT claim Phase 0.6 complete or first-edition 5/5 audited.
# NEVER sets process_split_authorized=true / product accuracy_claim=true.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
cd "$ROOT"

echo "== scorecard_v1_check =="
bash "$ROOT/scripts/scorecard_v1_check.sh"

echo "== accuracy honesty scan (scheme A) =="
"$PYTHON" "$ROOT/scripts/accuracy_honesty_scan.py"

echo "== package stable subset (python=$PYTHON) =="
PYTHONPATH=. "$PYTHON" -m pytest -q --tb=line \
  tests/test_scorecard_v1.py \
  tests/test_g2b_accuracy_closeout.py \
  tests/test_g2b_kappa.py \
  tests/test_calibration_human_pack.py \
  tests/test_preference_v0.py \
  tests/test_arch_consolidation_v1.py \
  tests/test_p1_composite_semantics.py

echo "== core g2b scheme A (python=$PYTHON) =="
cd "$REPO"
PYTHONPATH=aiPlat-core:packages/aiplat-evaluation "$PYTHON" -m pytest -q --tb=line \
  aiPlat-core/core/tests/unit/test_eval_g2b_pack_status.py \
  aiPlat-core/core/tests/unit/test_eval_g2b_l5_gap.py

echo "phase0 CI stable subset PASS (≠ Phase 0.6 / ≠ first-edition audited)"
