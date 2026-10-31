#!/usr/bin/env bash
# Scaffold unsigned live-*.json for all four ops tracks.
# Never sets production_signed=true. Never authorizes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="${AIPLAT_LIVE_SCAFFOLD_STAMP:-$(date -u +%Y%m%d)}"
ENV_NAME="${AIPLAT_LIVE_DRILL_ENV:-scaffold}"
OPERATOR="${AIPLAT_LIVE_DRILL_OPERATOR:-scaffold-bot}"

echo "== Ops live scaffold (unsigned only; does not authorize) =="

run_one() {
  local id="$1" script="$2"
  export AIPLAT_LIVE_DRILL_ID="$id"
  export AIPLAT_LIVE_DRILL_ENV="$ENV_NAME"
  export AIPLAT_LIVE_DRILL_OPERATOR="$OPERATOR"
  bash "$script"
}

run_one "scaffold-pgha-${STAMP}" packages/aiplat-central/scripts/pg_ha_record_live_drill.sh
run_one "scaffold-ontology-a3-${STAMP}" packages/aiplat-ontology/scripts/a3_record_live_drill.sh
run_one "scaffold-evaluation-a3-${STAMP}" packages/aiplat-evaluation/scripts/a3_record_live_drill.sh
run_one "scaffold-pi-d3-${STAMP}" packages/aiplat-pi-runtime/scripts/d3_record_live_drill.sh

echo "== verify unsigned =="
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "scripts/lib")
from aiplat_live_evidence import require_signed_live

dirs = [
    Path("packages/aiplat-central/docs/pg_ha/drills"),
    Path("packages/aiplat-ontology/docs/a3/drills"),
    Path("packages/aiplat-evaluation/docs/a3/drills"),
    Path("packages/aiplat-pi-runtime/docs/d3/drills"),
]
for d in dirs:
    ok, s = require_signed_live(d)
    assert ok is False, s
    assert s.get("live_count", 0) >= 1, s
    print("OK unsigned", d, "latest=", s.get("latest"))
print("PASS: ops_live_scaffold (all tracks have live-*.json; production_signed=false)")
PY

echo "NOTE: fill items → set production_signed=true → checklist ✅ → authorize"
echo "See reports/five-products/OPS_LIVE_RUNBOOK.md"
