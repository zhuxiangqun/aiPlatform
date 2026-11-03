#!/usr/bin/env bash
# Generate blank G2b + preference worksheets for two human annotators.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${AIPLAT_EVAL_HUMAN_PACK_OUT:-}"
# macOS bash 3.2 + set -u: avoid unbound "$@" when no args
if [[ -n "$OUT" ]]; then
  if [[ $# -gt 0 ]]; then
    PYTHONPATH=. python3 "$ROOT/scripts/human_worksheet_pack.py" --out "$OUT" "$@"
  else
    PYTHONPATH=. python3 "$ROOT/scripts/human_worksheet_pack.py" --out "$OUT"
  fi
else
  if [[ $# -gt 0 ]]; then
    PYTHONPATH=. python3 "$ROOT/scripts/human_worksheet_pack.py" "$@"
  else
    PYTHONPATH=. python3 "$ROOT/scripts/human_worksheet_pack.py"
  fi
fi
echo "human worksheet pack READY (fill facilitator model_output → send annotator sheets only)"
