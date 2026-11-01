#!/usr/bin/env bash
# Five-products D2 local performance baseline — wall-clock budgets only.
# Not production SLA. Does NOT authorize any hard gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

INCLUDE_SMOKE="${AIPLAT_PERF_INCLUDE_SMOKE:-0}"
CONTRACT_BUDGET_S="${AIPLAT_PERF_CONTRACT_BUDGET_S:-5}"
SMOKE_BUDGET_S="${AIPLAT_PERF_SMOKE_BUDGET_S:-30}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

run_budget() {
  local label="$1" budget="$2"; shift 2
  local start end elapsed
  start="$(date +%s)"
  "$@" || fail "$label exited non-zero"
  end="$(date +%s)"
  elapsed=$((end - start))
  if (( elapsed > budget )); then
    fail "$label took ${elapsed}s > budget ${budget}s"
  fi
  pass "$label ${elapsed}s (<=${budget}s)"
}

echo "== D2 local perf baseline (contract budget=${CONTRACT_BUDGET_S}s; smoke=${INCLUDE_SMOKE}) =="

run_budget "aiplat contracts" "$CONTRACT_BUDGET_S" \
  "$PY" reports/five-products/modules/aiplat/contracts/validate_sample.py
run_budget "ontology contracts" "$CONTRACT_BUDGET_S" \
  "$PY" reports/five-products/modules/ontology/contracts/validate_sample.py
run_budget "evaluation contracts" "$CONTRACT_BUDGET_S" \
  "$PY" reports/five-products/modules/evaluation/contracts/validate_sample.py
run_budget "fde contracts" "$CONTRACT_BUDGET_S" \
  "$PY" reports/five-products/modules/fde/contracts/validate_sample.py
run_budget "pi contracts" "$CONTRACT_BUDGET_S" \
  "$PY" reports/five-products/modules/pi/contracts/validate_sample.py
run_budget "diagnosis contracts" "$CONTRACT_BUDGET_S" \
  "$PY" reports/five-products/modules/diagnosis/contracts/validate_sample.py

for doc in \
  packages/aiplat-central/docs/PERF_BASELINE.md \
  packages/aiplat-pi-runtime/docs/PERF_BASELINE.md \
  packages/aiplat-fde/docs/PERF_BASELINE.md \
  packages/aiplat-ontology/docs/PERF_BASELINE.md \
  packages/aiplat-evaluation/docs/PERF_BASELINE.md \
  packages/aiplat-diagnosis/docs/PERF_BASELINE.md
do
  [[ -f "$doc" ]] || fail "missing $doc"
  grep -q "不是.*生产" "$doc" || grep -qi "not.*production\|不是生产" "$doc" \
    || fail "$doc must state not production SLA"
done
pass "PERF_BASELINE.md present for 6 packages"

if [[ "$INCLUDE_SMOKE" == "1" ]]; then
  run_budget "central d1_smoke" "$SMOKE_BUDGET_S" bash packages/aiplat-central/scripts/d1_smoke.sh
  run_budget "ontology d1_smoke" "$SMOKE_BUDGET_S" bash packages/aiplat-ontology/scripts/d1_smoke.sh
  run_budget "evaluation d1_smoke" "$SMOKE_BUDGET_S" bash packages/aiplat-evaluation/scripts/d1_smoke.sh
  run_budget "fde d1_smoke" "$SMOKE_BUDGET_S" bash packages/aiplat-fde/scripts/d1_smoke.sh
  run_budget "pi d1_smoke" "$SMOKE_BUDGET_S" bash packages/aiplat-pi-runtime/scripts/d1_smoke.sh
  run_budget "diagnosis d1_smoke" "$SMOKE_BUDGET_S" bash packages/aiplat-diagnosis/scripts/d1_smoke.sh
fi

pass "five_products local perf baseline"
echo "NOTE: local budgets only — production load requires real staging."
